from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from demandes.models import DemandeTransport
from demandes.views import _owned_demands
from .decorators import transporteur_required
from .forms import OffreTransportForm, SuiviForm, TrajetForm
from .models import OffreTransport, Trajet
from .services import RapportErreur, generer_pdf_rapport


def _verifier_offre_acceptation(demande, offre):
    """Revalide les contraintes qui peuvent changer depuis l'affichage du classement."""
    from datetime import datetime, time, timedelta
    from django.utils import timezone
    from vehicules.models import Disponibilite, Maintenance, Vehicule

    trajet = Trajet.objects.select_for_update().get(pk=offre.trajet_id)
    offre.trajet = trajet
    date_depart = timezone.localtime(trajet.date_depart).date()
    if trajet.statut != Trajet.Statut.PUBLIE or trajet.date_depart <= timezone.now():
        return 'Le trajet n’est plus disponible.'
    if date_depart < demande.date_depart or date_depart > demande.date_limite:
        return 'La date du trajet ne respecte plus la période de la demande.'

    vehicule = Vehicule.objects.select_for_update().filter(
        immatriculation__iexact=trajet.vehicule,
        transporteur=offre.transporteur,
    ).first()
    if vehicule is None or vehicule.statut != Vehicule.Statut.ACTIF:
        return 'Le véhicule lié au trajet n’est plus disponible.'

    poids = demande.marchandises.aggregate(total=Sum('poids'))['total']
    volume = demande.marchandises.aggregate(total=Sum('volume'))['total']
    if poids is None or poids <= 0:
        return 'Le poids des marchandises est manquant ou invalide.'
    if poids > trajet.capacite_kg or poids > vehicule.capacite_poids_kg:
        return 'La capacité de poids disponible est désormais insuffisante.'
    if volume is not None and (volume > trajet.volume_m3 or volume > vehicule.capacite_volume_m3):
        return 'La capacité de volume disponible est désormais insuffisante.'

    # La durée du trajet n'est pas stockée : les blocages déclarés et les trajets
    # déjà acceptés le jour du départ sont vérifiés sur la date connue.
    tz = timezone.get_current_timezone()
    debut = timezone.make_aware(datetime.combine(date_depart, time.min), tz)
    fin = debut + timedelta(days=1)
    if Disponibilite.objects.select_for_update().filter(
        vehicule=vehicule,
        statut=Disponibilite.Statut.INDISPONIBLE,
        date_debut__lt=fin,
        date_fin__gt=debut,
    ).exists():
        return 'Le véhicule est déclaré indisponible à la date du trajet.'
    if Maintenance.objects.select_for_update().filter(
        vehicule=vehicule,
        statut__in=[Maintenance.Statut.PLANIFIEE, Maintenance.Statut.EN_COURS],
        date_debut__lt=fin,
        date_fin__gt=debut,
    ).exists():
        return 'Une maintenance bloque le véhicule à la date du trajet.'
    if OffreTransport.objects.select_for_update().filter(
        trajet__vehicule__iexact=trajet.vehicule,
        trajet__date_depart__date=date_depart,
        statut=OffreTransport.Statut.ACCEPTEE,
    ).exclude(pk=offre.pk).exists():
        return 'Ce véhicule est déjà affecté à un transport accepté ce jour-là.'
    return None


def _demandes():
    return DemandeTransport.objects.filter(
        statut=DemandeTransport.Statut.OUVERTE
    ).exclude(offres_transport__statut=OffreTransport.Statut.ACCEPTEE).select_related('created_by').prefetch_related('marchandises')


@transporteur_required
def demandes(request):
    items = _demandes().annotate(deja_postule=Exists(
        OffreTransport.objects.filter(transporteur=request.user, demande=OuterRef('pk'))
    ))
    query = request.GET.get('q', '').strip()
    if query:
        items = items.filter(
            Q(depart_ville__icontains=query) | Q(arrivee_ville__icontains=query)
            | Q(marchandises__description__icontains=query) | Q(marchandises__type__icontains=query)
        ).distinct()
    return render(request, 'gestion_trajets_offres/demandes.html', {
        'active_tab': 'demandes', 'demandes': items, 'query': query, 'total_demandes': items.count(),
    })


@transporteur_required
def demande_detail(request, pk):
    demande = get_object_or_404(_demandes(), pk=pk)
    return render(request, 'gestion_trajets_offres/demande_detail.html', {
        'active_tab': 'demandes', 'demande': demande,
        'deja_postule': demande.offres_transport.filter(transporteur=request.user).exists(),
    })


@transporteur_required
def trajets(request):
    return render(request, 'gestion_trajets_offres/trajets.html', {
        'active_tab': 'trajets', 'trajets': Trajet.objects.filter(transporteur=request.user),
    })


@transporteur_required
@require_POST
def rapport_trajet(request, pk):
    trajet = get_object_or_404(Trajet, pk=pk, transporteur=request.user)
    try:
        pdf = generer_pdf_rapport(trajet)
    except RapportErreur as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="rapport-trajet-{trajet.pk}.pdf"'
    response['Cache-Control'] = 'no-store'
    return response


@transporteur_required
def offres(request):
    return render(request, 'gestion_trajets_offres/offres.html', {
        'active_tab': 'offres', 'offres': OffreTransport.objects.filter(transporteur=request.user).select_related('demande', 'trajet'),
    })


@transporteur_required
def transports(request):
    return render(request, 'gestion_trajets_offres/transports.html', {
        'active_tab': 'transports',
        'trajets': Trajet.objects.filter(transporteur=request.user).prefetch_related('offres__demande'),
    })


@transporteur_required
@require_http_methods(['GET', 'POST'])
def suivi_form(request, pk):
    trajet = get_object_or_404(Trajet, pk=pk, transporteur=request.user)
    form = SuiviForm(request.POST if request.method == 'POST' else None, instance=trajet)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return JsonResponse({'success': True})
    return _popup(request, {
        'form': form, 'title': 'Actualiser le suivi', 'subtitle': str(trajet), 'action': request.path,
    }, 422 if request.method == 'POST' else 200)


def _popup(request, context, status=200):
    html = render_to_string('gestion_trajets_offres/popup.html', context, request=request)
    return JsonResponse({'html': html}, status=status)


@require_GET
def demande_offres(request, pk):
    demande = get_object_or_404(_owned_demands(request), pk=pk)
    return _offres_popup(request, demande)


def _offres_popup(request, demande):
    html = render_to_string('gestion_trajets_offres/demande_offres.html', {
        'demande': demande,
    }, request=request)
    return JsonResponse({'html': html})


@require_POST
def accepter_offre(request, pk, offre_pk):
    with transaction.atomic():
        demande = get_object_or_404(_owned_demands(request).select_for_update(), pk=pk)
        offre = get_object_or_404(
            demande.offres_transport.select_related('trajet', 'transporteur'), pk=offre_pk,
        )
        if (demande.statut != DemandeTransport.Statut.OUVERTE
                or offre.statut != OffreTransport.Statut.EN_ATTENTE
                or demande.offres_transport.filter(statut=OffreTransport.Statut.ACCEPTEE).exists()):
            return JsonResponse({'error': 'Cette offre ne peut plus être acceptée.'}, status=409)
        erreur = _verifier_offre_acceptation(demande, offre)
        if erreur:
            return JsonResponse({'error': erreur}, status=409)
        offre.statut = OffreTransport.Statut.ACCEPTEE
        offre.save(update_fields=['statut', 'updated_at'])
        demande.offres_transport.filter(statut=OffreTransport.Statut.EN_ATTENTE).update(
            statut=OffreTransport.Statut.REFUSEE, updated_at=offre.updated_at,
        )
    return _offres_popup(request, demande)


@transporteur_required
@require_http_methods(['GET', 'POST'])
def trajet_form(request, pk=None):
    trajet = get_object_or_404(Trajet, pk=pk, transporteur=request.user) if pk else Trajet(transporteur=request.user)
    form = TrajetForm(request.POST if request.method == 'POST' else None, instance=trajet, transporteur=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return JsonResponse({'success': True})
    return _popup(request, {'form': form, 'title': 'Modifier le trajet' if pk else 'Publier un trajet', 'action': request.path}, 422 if request.method == 'POST' else 200)


@transporteur_required
@require_http_methods(['GET', 'POST'])
def offre_form(request, demande_pk=None, pk=None):
    if pk:
        offre = get_object_or_404(OffreTransport, pk=pk, transporteur=request.user)
        demande = offre.demande
        if offre.statut != OffreTransport.Statut.EN_ATTENTE:
            return JsonResponse({'error': 'Cette offre ne peut plus être modifiée.'}, status=409)
    else:
        demande = get_object_or_404(_demandes(), pk=demande_pk)
        offre = OffreTransport(transporteur=request.user, demande=demande)
    if (demande.statut != DemandeTransport.Statut.OUVERTE
            or demande.offres_transport.filter(statut=OffreTransport.Statut.ACCEPTEE).exists()):
        return JsonResponse({'error': 'Cette demande est fermée.'}, status=409)
    form = OffreTransportForm(request.POST if request.method == 'POST' else None, instance=offre, transporteur=request.user, demande=demande)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error(None, 'Vous avez déjà proposé une offre pour cette demande.')
        else:
            return JsonResponse({'success': True})
    return _popup(request, {
        'form': form, 'title': 'Modifier mon offre' if pk else 'Postuler à la demande',
        'subtitle': f'{demande} → {demande.depart_ville} → {demande.arrivee_ville}',
        'action': request.path, 'offer': True,
    }, 422 if request.method == 'POST' else 200)


@transporteur_required
@require_http_methods(['GET', 'POST'])
def supprimer(request, kind, pk):
    model = Trajet if kind == 'trajet' else OffreTransport
    obj = get_object_or_404(model, pk=pk, transporteur=request.user)
    if request.method == 'POST':
        if isinstance(obj, OffreTransport) and obj.statut != OffreTransport.Statut.EN_ATTENTE:
            return JsonResponse({'error': 'Seule une offre en attente peut être supprimée.'}, status=409)
        try:
            obj.delete()
        except ProtectedError:
            return JsonResponse({'error': 'Ce trajet est lié à des offres. Supprimez d’abord les offres en attente ; les offres acceptées doivent être conservées.'}, status=409)
        return JsonResponse({'success': True})
    return _popup(request, {'title': 'Confirmer la suppression', 'subtitle': str(obj), 'delete': True, 'action': request.path})

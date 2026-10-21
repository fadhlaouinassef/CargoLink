from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from demandes.models import DemandeTransport
from .decorators import transporteur_required
from .forms import OffreTransportForm, SuiviForm, TrajetForm
from .models import OffreTransport, Trajet


def _demandes():
    return DemandeTransport.objects.filter(
        statut=DemandeTransport.Statut.OUVERTE
    ).select_related('created_by').prefetch_related('marchandises')


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
    return render(request, 'gestion_trajets/demandes.html', {
        'active_tab': 'demandes', 'demandes': items, 'query': query, 'total_demandes': items.count(),
    })


@transporteur_required
def demande_detail(request, pk):
    demande = get_object_or_404(_demandes(), pk=pk)
    return render(request, 'gestion_trajets/demande_detail.html', {
        'active_tab': 'demandes', 'demande': demande,
        'deja_postule': demande.offres_transport.filter(transporteur=request.user).exists(),
    })


@transporteur_required
def trajets(request):
    return render(request, 'gestion_trajets/trajets.html', {
        'active_tab': 'trajets', 'trajets': Trajet.objects.filter(transporteur=request.user),
    })


@transporteur_required
def offres(request):
    return render(request, 'gestion_trajets/offres.html', {
        'active_tab': 'offres', 'offres': OffreTransport.objects.filter(transporteur=request.user).select_related('demande', 'trajet'),
    })


@transporteur_required
def transports(request):
    return render(request, 'gestion_trajets/transports.html', {
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
    html = render_to_string('gestion_trajets/popup.html', context, request=request)
    return JsonResponse({'html': html}, status=status)


@transporteur_required
@require_http_methods(['GET', 'POST'])
def trajet_form(request, pk=None):
    trajet = get_object_or_404(Trajet, pk=pk, transporteur=request.user) if pk else Trajet(transporteur=request.user)
    form = TrajetForm(request.POST if request.method == 'POST' else None, instance=trajet)
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
    if demande.statut != DemandeTransport.Statut.OUVERTE:
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

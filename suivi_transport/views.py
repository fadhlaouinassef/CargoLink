from functools import wraps
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from demandes.models import DemandeTransport
from gestion_trajets_offres.models import OffreTransport, Trajet
from gestion_trajets_offres.views import _verifier_offre_acceptation

from .forms import EvenementSuiviForm, IncidentTransportForm, TraitementIncidentForm
from .models import EvenementSuivi, HistoriqueIncident, IncidentTransport, Transport


def _role_required(role):
    def decorator(view):
        @login_required(login_url='authentification:login')
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role != role:
                return HttpResponseForbidden('Cette page ne fait pas partie de votre espace.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def _admin_required(view):
    @login_required(login_url='authentification:login')
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != 'admin':
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def _pme_access_required(view):
    return _role_required('PME')(view)


def _pme_scope(request):
    if request.user.is_authenticated:
        return Q(offre__demande__created_by=request.user)
    session_key = request.session.session_key
    return Q(offre__demande__owner_session=session_key) if session_key else Q(pk__isnull=True)


def pme_transports(request):
    return Transport.objects.filter(_pme_scope(request)).select_related(
        'offre__demande', 'offre__trajet', 'offre__transporteur'
    ).prefetch_related('evenements').distinct()


TRANSPORTEUR_EVENT_STATUSES = (
    Transport.Statut.PRIS_EN_CHARGE,
    Transport.Statut.EN_TRANSIT,
    Transport.Statut.ARRIVE,
    Transport.Statut.ANNULE,
)


def _carrier_transport(request, pk, *, lock=False):
    queryset = Transport.objects
    if lock:
        queryset = queryset.select_for_update()
    return get_object_or_404(queryset, pk=pk, offre__transporteur=request.user)


def _sync_transport_status(transport):
    events = transport.evenements.order_by('date_evenement', 'pk')
    # Ignore the legacy transport-status value `incident`; incidents now have
    # their own resolution workflow and this value must not affect the route.
    latest = events.exclude(statut='incident').last()
    transport.statut = latest.statut if latest else Transport.Statut.PLANIFIE
    if transport.date_confirmation_reception:
        transport.statut = Transport.Statut.LIVRE
    transport.date_prise_en_charge = events.filter(
        statut=Transport.Statut.PRIS_EN_CHARGE,
    ).values_list('date_evenement', flat=True).first()
    transport.date_arrivee = events.filter(
        statut__in=(Transport.Statut.ARRIVE, Transport.Statut.LIVRE),
    ).values_list('date_evenement', flat=True).first()
    transport.save(update_fields=[
        'statut', 'date_prise_en_charge', 'date_arrivee', 'updated_at',
    ])


def _admin_transports_queryset():
    return Transport.objects.select_related(
        'offre__demande', 'offre__trajet', 'offre__transporteur',
    ).prefetch_related('evenements')


@_admin_required
def admin_transports(request):
    transports = _admin_transports_queryset()
    query = request.GET.get('q', '').strip() or request.GET.get('reference', '').strip()
    status = request.GET.get('status', '').strip() or request.GET.get('statut', '').strip()
    transporter = (
        request.GET.get('transporter', '').strip()
        or request.GET.get('transporteur', '').strip()
    )
    destination = request.GET.get('destination', '').strip()

    if query:
        search_filter = (
            Q(offre__demande__arrivee_ville__icontains=query)
            | Q(offre__demande__arrivee_adresse__icontains=query)
            | Q(offre__transporteur__full_name__icontains=query)
            | Q(offre__transporteur__email__icontains=query)
        )
        reference = query.upper().replace('TR-', '').replace('DEM-', '').lstrip('#')
        if reference.isdigit():
            number = int(reference)
            search_filter |= Q(pk=number) | Q(offre__demande__pk=number)
        transports = transports.filter(search_filter)
    if status in Transport.Statut.values:
        transports = transports.filter(statut=status)
    if transporter.isdigit():
        transports = transports.filter(offre__transporteur_id=int(transporter))
    if destination:
        transports = transports.filter(offre__demande__arrivee_ville__icontains=destination)

    user_model = request.user.__class__
    transporteurs = user_model.objects.filter(
        role='transporteur', is_active=True,
    ).order_by('full_name', 'email')
    return render(request, 'dashboard/admin-transports.html', {
        'transports': transports,
        'query': query,
        'selected_status': status,
        'selected_transporter': transporter,
        'selected_destination': destination,
        'status_choices': Transport.Statut.choices,
        'transporteurs': transporteurs,
        'total_transports': Transport.objects.count(),
        'active_transports': Transport.objects.exclude(
            statut__in=(Transport.Statut.LIVRE, Transport.Statut.ANNULE),
        ).count(),
        'incident_transports': IncidentTransport.objects.exclude(
            etat=IncidentTransport.Etat.RESOLU,
        ).count(),
    })


@_admin_required
def admin_transport_detail(request, pk):
    transport = get_object_or_404(_admin_transports_queryset(), pk=pk)
    return render(request, 'dashboard/admin-transport-detail.html', {
        'transport': transport,
        'form': EvenementSuiviForm(initial={
            'statut': transport.statut,
            'date_evenement': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        }),
    })


@_admin_required
@require_POST
def admin_transport_event(request, pk):
    with transaction.atomic():
        transport = get_object_or_404(
            Transport.objects.select_for_update(), pk=pk,
        )
        form = EvenementSuiviForm(request.POST)
        if not form.is_valid():
            transport = get_object_or_404(_admin_transports_queryset(), pk=pk)
            return render(request, 'dashboard/admin-transport-detail.html', {
                'transport': transport, 'form': form,
            }, status=422)
        event = form.save(commit=False)
        event.transport = transport
        event.cree_par = request.user
        event.save()
        _sync_transport_status(transport)
        messages.success(request, f'Événement « {event.titre} » enregistré.')
    return redirect('authentification:admin_transport_detail', pk=pk)


@_admin_required
@require_http_methods(['GET', 'POST'])
def admin_transport_event_edit(request, pk, event_pk):
    transport = get_object_or_404(Transport.objects.all(), pk=pk)
    event = get_object_or_404(EvenementSuivi, pk=event_pk, transport=transport)
    form = EvenementSuiviForm(
        request.POST if request.method == 'POST' else None,
        instance=event,
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            transport = get_object_or_404(
                Transport.objects.select_for_update(), pk=pk,
            )
            event = get_object_or_404(
                EvenementSuivi, pk=event_pk, transport=transport,
            )
            form = EvenementSuiviForm(request.POST, instance=event)
            event = form.save()
            _sync_transport_status(transport)
        messages.success(request, f'Événement « {event.titre} » corrigé.')
        return redirect('authentification:admin_transport_detail', pk=pk)
    return render(request, 'dashboard/admin-transport-detail.html', {
        'transport': _admin_transports_queryset().get(pk=pk),
        'form': form,
        'edit_event': event,
        'edit_form': form,
    }, status=422 if request.method == 'POST' else 200)


@_admin_required
@require_POST
def admin_transport_event_delete(request, pk, event_pk):
    with transaction.atomic():
        transport = get_object_or_404(
            Transport.objects.select_for_update(), pk=pk,
        )
        event = get_object_or_404(
            EvenementSuivi, pk=event_pk, transport=transport,
        )
        event.delete()
        _sync_transport_status(transport)
    messages.success(request, 'Événement supprimé.')
    return redirect('authentification:admin_transport_detail', pk=pk)


@_pme_access_required
def pme_list(request):
    return render(request, 'suivi_transport/pme_list.html', {
        'active_tab': 'transports_list', 'transports': pme_transports(request),
    })


@_pme_access_required
def pme_detail(request, pk):
    transport = get_object_or_404(
        pme_transports(request).prefetch_related('incidents__historique__auteur'), pk=pk,
    )
    incident_remplacement = None
    if (transport.statut != Transport.Statut.ANNULE
            and not transport.date_confirmation_reception
            and transport.offre.statut == OffreTransport.Statut.ACCEPTEE):
        incident_remplacement = transport.incidents.filter(
            categorie__in=[IncidentTransport.Categorie.ACCIDENT, IncidentTransport.Categorie.PANNE],
        ).exclude(etat=IncidentTransport.Etat.RESOLU).first()
    offres_recommandees = OffreTransport.objects.none()
    if incident_remplacement:
        marchandises = transport.demande.marchandises.aggregate(
            poids_total=Sum('poids'), volume_total=Sum('volume'),
            nombre=Count('pk'), volumes_renseignes=Count('volume'),
        )
        if marchandises['poids_total'] is not None:
            offres_recommandees = OffreTransport.objects.filter(
                demande=transport.demande,
                statut=OffreTransport.Statut.REFUSEE,
                trajet__statut=Trajet.Statut.PUBLIE,
                trajet__depart_ville__iexact=transport.trajet.depart_ville.strip(),
                trajet__arrivee_ville__iexact=transport.trajet.arrivee_ville.strip(),
                trajet__date_depart__gte=timezone.now(),
                trajet__capacite_kg__gte=marchandises['poids_total'],
                transporteur__role='transporteur',
                transport_suivi__isnull=True,
            ).exclude(transporteur_id=transport.offre.transporteur_id)
        if (marchandises['volume_total'] is not None
                and marchandises['volumes_renseignes'] == marchandises['nombre']):
            offres_recommandees = offres_recommandees.filter(
                trajet__volume_m3__gte=marchandises['volume_total'],
            )
        offres_recommandees = offres_recommandees.select_related(
            'transporteur', 'trajet',
        ).order_by('trajet__date_depart', 'prix')[:5]
    return render(request, 'suivi_transport/pme_detail.html', {
        'active_tab': 'transports_list', 'transport': transport,
        'incident_remplacement': incident_remplacement,
        'offres_recommandees': offres_recommandees,
    })


@_pme_access_required
@require_POST
def accepter_offre_remplacement(request, pk, offre_pk):
    with transaction.atomic():
        transport_actuel = get_object_or_404(
            Transport.objects.select_for_update().select_related(
                'offre__trajet', 'offre__transporteur',
            ).filter(_pme_scope(request)),
            pk=pk,
        )
        demande = get_object_or_404(
            DemandeTransport.objects.select_for_update(),
            pk=transport_actuel.offre.demande_id, created_by=request.user,
        )
        offre = get_object_or_404(
            OffreTransport.objects.select_for_update(of=('self',)).select_related(
                'trajet', 'transporteur',
            ),
            pk=offre_pk, demande=demande, statut=OffreTransport.Statut.REFUSEE,
            transport_suivi__isnull=True,
        )
        incident_actif = transport_actuel.incidents.filter(
            categorie__in=[IncidentTransport.Categorie.ACCIDENT, IncidentTransport.Categorie.PANNE],
        ).exclude(etat=IncidentTransport.Etat.RESOLU).exists()
        trajet_actuel = transport_actuel.trajet
        meme_itineraire = (
            offre.trajet.depart_ville.strip().casefold() == trajet_actuel.depart_ville.strip().casefold()
            and offre.trajet.arrivee_ville.strip().casefold() == trajet_actuel.arrivee_ville.strip().casefold()
        )
        if (not incident_actif or transport_actuel.statut == Transport.Statut.ANNULE
                or transport_actuel.date_confirmation_reception
                or transport_actuel.offre.statut != OffreTransport.Statut.ACCEPTEE
                or offre.transporteur_id == transport_actuel.offre.transporteur_id
                or not meme_itineraire):
            messages.error(request, 'Cette offre de remplacement ne peut plus être acceptée.')
            return redirect('pme:transport_detail', pk=pk)

        erreur = _verifier_offre_acceptation(demande, offre)
        if erreur:
            messages.error(request, erreur)
            return redirect('pme:transport_detail', pk=pk)

        ancien_transporteur = transport_actuel.offre.transporteur.full_name or transport_actuel.offre.transporteur.email
        transport_actuel.statut = Transport.Statut.ANNULE
        transport_actuel.save(update_fields=['statut', 'updated_at'])
        EvenementSuivi.objects.create(
            transport=transport_actuel,
            statut=Transport.Statut.ANNULE,
            titre='Transport annulé — remplacé après incident',
            description='La PME a accepté une nouvelle offre de remplacement.',
            cree_par=request.user,
        )
        transport_actuel.offre.statut = OffreTransport.Statut.REFUSEE
        transport_actuel.offre.save(update_fields=['statut', 'updated_at'])
        offre.statut = OffreTransport.Statut.ACCEPTEE
        offre.save(update_fields=['statut', 'updated_at'])
        nouveau_transport = Transport.objects.get(offre=offre)
        evenement_nouveau_transport = EvenementSuivi.objects.filter(
            transport=nouveau_transport,
        ).latest('pk')
        evenement_nouveau_transport.titre = 'Transport de remplacement planifie'
        evenement_nouveau_transport.description = (
            f'Ce transport remplace {transport_actuel} apres un incident. '
            f'Offre de {offre.prix} TND acceptee par la PME.'
        )
        evenement_nouveau_transport.save(update_fields=['titre', 'description'])
        evenement_annulation = EvenementSuivi.objects.filter(transport=transport_actuel).latest('pk')
        evenement_annulation.description = (
            f'Ancien transporteur : {ancien_transporteur}. Le transport de remplacement '
            f'{nouveau_transport} a été accepté par la PME.'
        )
        evenement_annulation.save(update_fields=['description'])
        messages.success(request, f'L’offre de remplacement a été acceptée. Le suivi continue sur {nouveau_transport}.')
    return redirect('pme:transport_detail', pk=nouveau_transport.pk)


@_pme_access_required
@require_POST
def confirmer_reception(request, pk):
    transport = get_object_or_404(Transport, _pme_scope(request), pk=pk)
    if transport.date_confirmation_reception:
        return redirect('pme:transport_detail', pk=pk)
    if transport.statut not in (Transport.Statut.ARRIVE, Transport.Statut.LIVRE):
        return HttpResponseForbidden('La réception sera disponible après l’arrivée du transport.')
    with transaction.atomic():
        transport = get_object_or_404(
            Transport.objects.select_for_update(), _pme_scope(request), pk=pk,
        )
        if not transport.date_confirmation_reception:
            now = timezone.now()
            transport.date_confirmation_reception = now
            transport.statut = Transport.Statut.LIVRE
            transport.save(update_fields=['date_confirmation_reception', 'statut', 'updated_at'])
            EvenementSuivi.objects.create(
                transport=transport, statut=Transport.Statut.LIVRE,
                titre='Réception confirmée',
                description='La PME a confirmé la bonne réception.',
                date_evenement=now,
                cree_par=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, 'La réception de la marchandise a été confirmée.')
    return redirect('pme:transport_detail', pk=pk)


@_role_required('transporteur')
def transporteur_list(request):
    transports = Transport.objects.filter(offre__transporteur=request.user).select_related(
        'offre__demande', 'offre__trajet', 'offre__transporteur'
    ).prefetch_related('evenements')
    trajets = Trajet.objects.filter(transporteur=request.user).prefetch_related('offres__demande')
    return render(request, 'suivi_transport/transporteur_list.html', {
        'active_tab': 'transports', 'transports': transports, 'trajets': trajets,
    })


@_role_required('transporteur')
def transporteur_detail(request, pk):
    transport = get_object_or_404(
        Transport.objects.select_related('offre__demande', 'offre__trajet', 'offre__transporteur')
        .prefetch_related('evenements', 'incidents__historique__auteur'), pk=pk,
        offre__transporteur=request.user,
    )
    return render(request, 'suivi_transport/transporteur_detail.html', {
        'active_tab': 'transports',
        'transport': transport,
        'form': EvenementSuiviForm(initial={
            'statut': transport.statut,
            'date_evenement': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        }, allowed_statuses=TRANSPORTEUR_EVENT_STATUSES),
    })


@_role_required('transporteur')
@require_POST
def ajouter_evenement(request, pk):
    with transaction.atomic():
        transport = _carrier_transport(request, pk, lock=True)
        if transport.date_confirmation_reception:
            return HttpResponseForbidden('Le suivi est clôturé après confirmation de réception.')
        if transport.statut == Transport.Statut.ANNULE:
            return HttpResponseForbidden('Le suivi ne peut plus être modifié pour un transport annulé.')
        form = EvenementSuiviForm(
            request.POST, allowed_statuses=TRANSPORTEUR_EVENT_STATUSES,
        )
        if not form.is_valid():
            transport = get_object_or_404(
                Transport.objects.select_related('offre__demande', 'offre__trajet', 'offre__transporteur')
                .prefetch_related('evenements', 'incidents__historique__auteur'),
                pk=pk, offre__transporteur=request.user,
            )
            return render(request, 'suivi_transport/transporteur_detail.html', {
                'active_tab': 'transports', 'transport': transport, 'form': form,
            }, status=422)
        event = form.save(commit=False)
        event.transport = transport
        event.cree_par = request.user
        event.save()
        _sync_transport_status(transport)
        messages.success(request, f'Événement « {event.titre} » enregistré.')
    return redirect('transporteur:transport_detail', pk=pk)


@_role_required('transporteur')
@require_http_methods(['GET', 'POST'])
def modifier_evenement(request, pk, event_pk):
    transport = _carrier_transport(request, pk)
    event = get_object_or_404(
        EvenementSuivi, pk=event_pk, transport=transport, cree_par=request.user,
    )
    if transport.date_confirmation_reception:
        return HttpResponseForbidden('Le suivi est clôturé après confirmation de réception.')
    form = EvenementSuiviForm(
        request.POST if request.method == 'POST' else None,
        instance=event,
        allowed_statuses=TRANSPORTEUR_EVENT_STATUSES,
    )
    if request.method == 'POST':
        with transaction.atomic():
            transport = _carrier_transport(request, pk, lock=True)
            event = get_object_or_404(
                EvenementSuivi, pk=event_pk, transport=transport, cree_par=request.user,
            )
            form = EvenementSuiviForm(
                request.POST, instance=event,
                allowed_statuses=TRANSPORTEUR_EVENT_STATUSES,
            )
            if form.is_valid():
                form.save()
                _sync_transport_status(transport)
                messages.success(request, f'Événement « {event.titre} » corrigé.')
                return redirect('transporteur:transport_detail', pk=pk)
    if request.method == 'POST':
        messages.error(request, 'Les données de l’événement sont invalides.')
    transport = Transport.objects.select_related(
        'offre__demande', 'offre__trajet', 'offre__transporteur',
    ).prefetch_related('evenements', 'incidents__historique__auteur').get(pk=pk)
    return render(request, 'suivi_transport/transporteur_detail.html', {
        'active_tab': 'transports',
        'transport': transport,
        'form': EvenementSuiviForm(
            initial={'statut': transport.statut,
                     'date_evenement': timezone.localtime().strftime('%Y-%m-%dT%H:%M')},
            allowed_statuses=TRANSPORTEUR_EVENT_STATUSES,
        ),
        'edit_event': event,
        'edit_form': form,
    }, status=422 if request.method == 'POST' else 200)


@_role_required('transporteur')
@require_POST
def supprimer_evenement(request, pk, event_pk):
    with transaction.atomic():
        transport = _carrier_transport(request, pk, lock=True)
        if transport.date_confirmation_reception:
            return HttpResponseForbidden('Le suivi est clôturé après confirmation de réception.')
        event = get_object_or_404(
            EvenementSuivi, pk=event_pk, transport=transport, cree_par=request.user,
        )
        event.delete()
        _sync_transport_status(transport)
        messages.success(request, 'Événement supprimé.')
    return redirect('transporteur:transport_detail', pk=pk)


@_role_required('transporteur')
@require_POST
def supprimer_transport(request, pk):
    transport = _carrier_transport(request, pk)
    if (transport.date_prise_en_charge or transport.date_arrivee
            or transport.date_confirmation_reception
            or transport.evenements.exclude(statut=Transport.Statut.PLANIFIE).exists()):
        return HttpResponseForbidden('Un transport commencé ou suivi ne peut pas être supprimé.')
    transport.delete()
    messages.success(request, 'Le transport planifié a été supprimé.')
    return redirect('transporteur:transports')


@_role_required('transporteur')
@require_http_methods(['GET', 'POST'])
def signaler_incident(request, pk):
    transport = _carrier_transport(request, pk)
    if transport.date_confirmation_reception or transport.statut == Transport.Statut.ANNULE:
        return HttpResponseForbidden('Un incident ne peut plus être signalé sur un transport clôturé.')

    form = IncidentTransportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            transport = _carrier_transport(request, pk, lock=True)
            if transport.date_confirmation_reception or transport.statut == Transport.Statut.ANNULE:
                return HttpResponseForbidden('Un incident ne peut plus être signalé sur un transport clôturé.')
            incident = form.save(commit=False)
            incident.transport = transport
            incident.signale_par = request.user
            incident.save()
            HistoriqueIncident.objects.create(
                incident=incident, etat=incident.etat, auteur=request.user,
                commentaire='Incident signalé par le transporteur.',
            )
        messages.success(request, 'Votre incident a été signalé. Son suivi est disponible sur cette page.')
        return redirect('transporteur:transport_detail', pk=pk)
    return render(request, 'suivi_transport/incident_form.html', {
        'transport': transport, 'form': form,
    }, status=422 if request.method == 'POST' else 200)


@_admin_required
def admin_incidents(request):
    incidents = IncidentTransport.objects.select_related(
        'transport__offre__demande', 'transport__offre__trajet',
        'transport__offre__transporteur', 'signale_par',
    )
    query = request.GET.get('q', '').strip()
    etat = request.GET.get('etat', '').strip()
    priorite = request.GET.get('priorite', '').strip()
    categorie = request.GET.get('categorie', '').strip()
    if query:
        filtres = (
            Q(description__icontains=query)
            | Q(transport__offre__transporteur__full_name__icontains=query)
            | Q(transport__offre__transporteur__email__icontains=query)
            | Q(transport__offre__demande__arrivee_ville__icontains=query)
        )
        reference = query.upper().replace('TR-', '').replace('INC-', '').lstrip('#')
        if reference.isdigit():
            filtres |= Q(pk=int(reference)) | Q(transport_id=int(reference))
        incidents = incidents.filter(filtres)
    if etat in IncidentTransport.Etat.values:
        incidents = incidents.filter(etat=etat)
    if priorite in IncidentTransport.Priorite.values:
        incidents = incidents.filter(priorite=priorite)
    if categorie in IncidentTransport.Categorie.values:
        incidents = incidents.filter(categorie=categorie)
    return render(request, 'dashboard/admin-incidents.html', {
        'incidents': incidents,
        'query': query,
        'selected_etat': etat,
        'selected_etat_label': dict(IncidentTransport.Etat.choices).get(etat),
        'selected_priorite': priorite,
        'selected_priorite_label': dict(IncidentTransport.Priorite.choices).get(priorite),
        'selected_categorie': categorie,
        'selected_categorie_label': dict(IncidentTransport.Categorie.choices).get(categorie),
        'etat_choices': IncidentTransport.Etat.choices,
        'priorite_choices': IncidentTransport.Priorite.choices,
        'categorie_choices': IncidentTransport.Categorie.choices,
        'total_incidents': IncidentTransport.objects.count(),
        'open_incidents': IncidentTransport.objects.exclude(etat=IncidentTransport.Etat.RESOLU).count(),
        'urgent_incidents': IncidentTransport.objects.filter(
            priorite=IncidentTransport.Priorite.URGENTE,
        ).exclude(etat=IncidentTransport.Etat.RESOLU).count(),
    })


@_admin_required
def admin_incident_detail(request, pk):
    incident = get_object_or_404(
        IncidentTransport.objects.select_related(
            'transport__offre__demande', 'transport__offre__trajet',
            'transport__offre__transporteur', 'signale_par',
        ).prefetch_related('historique__auteur'), pk=pk,
    )
    return render(request, 'dashboard/admin-incident-detail.html', {
        'incident': incident,
        'form': TraitementIncidentForm(initial={'etat': incident.etat}),
    })


@_admin_required
@require_POST
def admin_incident_update(request, pk):
    form = TraitementIncidentForm(request.POST)
    if not form.is_valid():
        incident = get_object_or_404(IncidentTransport, pk=pk)
        return render(request, 'dashboard/admin-incident-detail.html', {
            'incident': incident, 'form': form,
        }, status=422)
    with transaction.atomic():
        incident = get_object_or_404(
            IncidentTransport.objects.select_for_update().select_related(
                'transport__offre__demande', 'transport__offre__trajet',
                'transport__offre__transporteur', 'signale_par',
            ).prefetch_related('historique__auteur'), pk=pk,
        )
        nouvel_etat = form.cleaned_data['etat']
        commentaire = form.cleaned_data['commentaire'].strip()
        ancien_etat = incident.etat
        incident.etat = nouvel_etat
        if nouvel_etat == IncidentTransport.Etat.RESOLU:
            incident.resolved_at = incident.resolved_at or timezone.now()
        else:
            incident.resolved_at = None
        incident.save(update_fields=['etat', 'resolved_at', 'updated_at'])
        if ancien_etat != nouvel_etat or commentaire:
            HistoriqueIncident.objects.create(
                incident=incident, etat=nouvel_etat, commentaire=commentaire,
                auteur=request.user,
            )
    messages.success(request, 'Le suivi de l’incident a été mis à jour.')
    return redirect('authentification:admin_incident_detail', pk=pk)


@login_required(login_url='authentification:login')
def photo_incident(request, pk):
    incident = get_object_or_404(
        IncidentTransport.objects.select_related('transport__offre__demande', 'transport__offre__transporteur'),
        pk=pk,
    )
    role = request.user.role
    allowed = (
        role == 'admin'
        or (role == 'transporteur' and incident.transport.offre.transporteur_id == request.user.pk)
        or (role == 'PME' and incident.transport.offre.demande.created_by_id == request.user.pk)
    )
    if not allowed:
        raise Http404
    if not incident.photo:
        raise Http404
    content_type = mimetypes.guess_type(incident.photo.name)[0] or 'application/octet-stream'
    response = FileResponse(incident.photo.open('rb'), content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline'
    return response

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from gestion_trajets_offres.models import Trajet

from .forms import EvenementSuiviForm
from .models import EvenementSuivi, Transport


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


def _pme_access_required(view):
    return _role_required('PME')(view)


def _pme_scope(request):
    if request.user.is_authenticated:
        scope = Q(offre__demande__created_by=request.user)
    else:
        scope = Q(pk__isnull=True)
    session_key = request.session.session_key
    if session_key:
        scope |= Q(offre__demande__owner_session=session_key)
    return scope


def pme_transports(request):
    return Transport.objects.filter(_pme_scope(request)).select_related(
        'offre__demande', 'offre__trajet', 'offre__transporteur'
    ).prefetch_related('evenements').distinct()


TRANSPORTEUR_EVENT_STATUSES = (
    Transport.Statut.PRIS_EN_CHARGE,
    Transport.Statut.EN_TRANSIT,
    Transport.Statut.ARRIVE,
    Transport.Statut.INCIDENT,
    Transport.Statut.ANNULE,
)


def _carrier_transport(request, pk, *, lock=False):
    queryset = Transport.objects
    if lock:
        queryset = queryset.select_for_update()
    return get_object_or_404(queryset, pk=pk, offre__transporteur=request.user)


def _sync_transport_status(transport):
    events = transport.evenements.order_by('date_evenement', 'pk')
    latest = events.last()
    if latest:
        transport.statut = latest.statut
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


@_pme_access_required
def pme_list(request):
    return render(request, 'suivi_transport/pme_list.html', {
        'active_tab': 'transports_list', 'transports': pme_transports(request),
    })


@_pme_access_required
def pme_detail(request, pk):
    transport = get_object_or_404(pme_transports(request), pk=pk)
    return render(request, 'suivi_transport/pme_detail.html', {
        'active_tab': 'transports_list', 'transport': transport,
    })


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
        .prefetch_related('evenements'), pk=pk, offre__transporteur=request.user,
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
                .prefetch_related('evenements'), pk=pk, offre__transporteur=request.user,
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
    return render(request, 'suivi_transport/transporteur_detail.html', {
        'active_tab': 'transports',
        'transport': Transport.objects.select_related(
            'offre__demande', 'offre__trajet', 'offre__transporteur',
        ).prefetch_related('evenements').get(pk=pk),
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

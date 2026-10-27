from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from authentification.decorators import role_required
from authentification.models import User
from suivi_transport.models import EvenementSuivi, Transport


def _recipient_transports(request):
    recipient_name = request.user.full_name.strip()
    return Transport.objects.filter(
        Q(offre__demande__destinataire_contact__iexact=recipient_name)
        | Q(offre__demande__destinataire_nom__iexact=recipient_name)
    ).select_related(
        'offre__demande', 'offre__trajet', 'offre__transporteur',
    ).prefetch_related('offre__demande__marchandises', 'evenements', 'incidents__historique')


def _latest_transport_position(transport):
    positions = [
        (event.date_evenement, event.latitude, event.longitude)
        for event in transport.evenements.all()
        if event.latitude is not None and event.longitude is not None
    ]
    positions.extend(
        (incident.created_at, incident.latitude, incident.longitude)
        for incident in transport.incidents.all()
        if incident.latitude is not None and incident.longitude is not None
    )
    if not positions:
        return None
    recorded_at, latitude, longitude = max(positions, key=lambda item: item[0])
    return {'date': recorded_at, 'latitude': latitude, 'longitude': longitude}

@role_required(User.Role.DESTINATAIRE)
def dashboard(request):
    transports = _recipient_transports(request)
    return render(request, 'destinataire/dashboard.html', {
        'active_tab': 'dashboard',
        'transports': transports,
        'active_transports': transports.exclude(statut__in=(Transport.Statut.LIVRE, Transport.Statut.ANNULE)),
        'pending_confirmations': transports.filter(
            statut__in=(Transport.Statut.ARRIVE, Transport.Statut.LIVRE),
            date_confirmation_reception__isnull=True,
        ).count(),
    })


@role_required(User.Role.DESTINATAIRE)
def suivi(request):
    return render(request, 'destinataire/suivi_livraison.html', {
        'active_tab': 'suivi',
        'transports': _recipient_transports(request),
    })


@role_required(User.Role.DESTINATAIRE)
def suivi_detail(request, pk):
    transport = get_object_or_404(_recipient_transports(request), pk=pk)
    return render(request, 'destinataire/suivi_detail.html', {
        'active_tab': 'suivi', 'transport': transport,
        'latest_position': _latest_transport_position(transport),
    })


@role_required(User.Role.DESTINATAIRE)
@require_POST
def confirmer_reception(request, pk):
    recipient_name = request.user.full_name.strip()
    with transaction.atomic():
        transport = get_object_or_404(
            Transport.objects.select_for_update().filter(
                Q(offre__demande__destinataire_contact__iexact=recipient_name)
                | Q(offre__demande__destinataire_nom__iexact=recipient_name)
            ), pk=pk,
        )
        if not transport.date_confirmation_reception and transport.statut in (
            Transport.Statut.ARRIVE, Transport.Statut.LIVRE,
        ):
            now = timezone.now()
            transport.date_confirmation_reception = now
            transport.statut = Transport.Statut.LIVRE
            transport.save(update_fields=['date_confirmation_reception', 'statut', 'updated_at'])
            EvenementSuivi.objects.create(
                transport=transport, statut=Transport.Statut.LIVRE,
                titre='Réception confirmée par le destinataire',
                description=f'Réception confirmée par {request.user.full_name}.',
                date_evenement=now, cree_par=request.user,
            )
            messages.success(request, 'La réception de la marchandise a été confirmée.')
        else:
            messages.info(request, 'La réception ne peut pas encore être confirmée.')
    return redirect('destinataire:suivi_detail', pk=pk)


@role_required(User.Role.DESTINATAIRE)
@require_GET
def confirmation(request):
    if request.method == 'POST':
        messages.success(request, "Livraison #TR-8842 confirmée avec succès ! Le récépissé d'émargement a été transmis à l'expéditeur et au transporteur.")
        return redirect('destinataire:dashboard')
    return render(request, 'destinataire/confirmations.html', {
        'active_tab': 'confirmation',
        'transports': _recipient_transports(request),
        'arrived_transports': _recipient_transports(request).filter(
            statut__in=(Transport.Statut.ARRIVE, Transport.Statut.LIVRE),
        ),
    })

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DemandeTransportForm, MarchandiseFormSet
from .models import DemandeTransport


def _owned_demands(request):
    if request.user.is_authenticated:
        return DemandeTransport.objects.filter(created_by=request.user)
    if request.session.session_key:
        return DemandeTransport.objects.filter(owner_session=request.session.session_key)
    return DemandeTransport.objects.none()


def dashboard(request):
    demandes = _owned_demands(request).prefetch_related('marchandises')
    return render(request, 'pme/dashboard.html', {
        'active_tab': 'dashboard',
        'demandes_recentes': demandes[:5],
        'total_demandes': demandes.count(),
        'demandes_ouvertes': demandes.filter(statut=DemandeTransport.Statut.OUVERTE).count(),
        'brouillons': demandes.filter(statut=DemandeTransport.Statut.BROUILLON).count(),
    })


def demande_create(request):
    form = DemandeTransportForm(request.POST or None)
    formset = MarchandiseFormSet(request.POST or None, prefix='marchandises')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        if not request.user.is_authenticated and not request.session.session_key:
            request.session.create()
        with transaction.atomic():
            demande = form.save(commit=False)
            demande.statut = (
                DemandeTransport.Statut.BROUILLON
                if request.POST.get('action') == 'draft'
                else DemandeTransport.Statut.OUVERTE
            )
            if request.user.is_authenticated:
                demande.created_by = request.user
            else:
                demande.owner_session = request.session.session_key
            demande.save()
            formset.instance = demande
            formset.save()
        if demande.statut == DemandeTransport.Statut.BROUILLON:
            messages.info(request, 'Votre demande a été enregistrée comme brouillon.')
        else:
            messages.success(request, 'Votre demande de transport a été publiée. Les transporteurs peuvent maintenant vous proposer leurs offres.')
        return redirect('pme:demandes_list')
    return render(request, 'demandes/demande_create.html', {
        'active_tab': 'demande_create',
        'form': form,
        'formset': formset,
    })


def demandes_list(request):
    demandes = _owned_demands(request).prefetch_related('marchandises')
    query = request.GET.get('q', '').strip()
    statut = request.GET.get('status', '').strip()
    if query:
        query_filter = (
            Q(depart_ville__icontains=query)
            | Q(arrivee_ville__icontains=query)
            | Q(destinataire_nom__icontains=query)
        )
        numeric_reference = query.rsplit('-', 1)[-1].lstrip('#')
        if numeric_reference.isdigit():
            query_filter |= Q(pk=int(numeric_reference))
        demandes = demandes.filter(query_filter)
    if statut in DemandeTransport.Statut.values:
        demandes = demandes.filter(statut=statut)
    return render(request, 'demandes/demandes_list.html', {
        'active_tab': 'demandes_list',
        'demandes': demandes,
        'query': query,
        'status': statut,
        'total_demandes': _owned_demands(request).count(),
    })


def demande_detail(request, pk=None):
    demands = _owned_demands(request).prefetch_related('marchandises')
    if pk is None:
        demande = demands.first()
        if demande is None:
            return demandes_list(request)
    else:
        demande = get_object_or_404(demands, pk=pk)
    return render(request, 'demandes/demande_detail.html', {
        'active_tab': 'demandes_list',
        'demande': demande,
    })

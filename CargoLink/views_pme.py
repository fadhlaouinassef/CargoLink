from django.contrib import messages
from django.shortcuts import redirect, render


def dashboard(request):
    return render(request, 'pme/dashboard.html', {
        'active_tab': 'dashboard',
    })


def demande_create(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'publish')
        if action == 'draft':
            messages.info(request, "Votre demande a été enregistrée comme brouillon.")
        else:
            messages.success(request, "Votre demande de transport a été publiée avec succès ! Les transporteurs peuvent désormais vous soumettre leurs offres.")
        return redirect('pme:demandes_list')
    return render(request, 'pme/demande_create.html', {
        'active_tab': 'demande_create',
    })


def demandes_list(request):
    return render(request, 'pme/demandes_list.html', {
        'active_tab': 'demandes_list',
    })


def demande_detail(request):
    return render(request, 'pme/demande_detail.html', {
        'active_tab': 'demandes_list',
    })


def offres_comparer(request):
    return render(request, 'pme/offres_comparer.html', {
        'active_tab': 'offres_comparer',
    })


def transports_list(request):
    return render(request, 'pme/transport_suivi.html', {
        'active_tab': 'transports_list',
    })


def transport_suivi(request):
    return render(request, 'pme/transport_suivi.html', {
        'active_tab': 'transports_list',
    })


def avis_create(request):
    if request.method == 'POST':
        messages.success(request, "Merci ! Votre évaluation a été enregistrée et publiée sur le profil du transporteur.")
        return redirect('pme:dashboard')
    return render(request, 'pme/avis_create.html', {
        'active_tab': 'avis_create',
    })


def reclamation_create(request):
    if request.method == 'POST':
        messages.warning(request, "Votre réclamation a été transmise à l'administrateur CargoLink pour instruction (Dossier #REC-2026-04).")
        return redirect('pme:dashboard')
    return render(request, 'pme/reclamation_create.html', {
        'active_tab': 'reclamation_create',
    })

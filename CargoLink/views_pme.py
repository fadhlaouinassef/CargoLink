from django.contrib import messages
from django.shortcuts import redirect, render


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

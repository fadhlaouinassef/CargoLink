from django.shortcuts import render


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

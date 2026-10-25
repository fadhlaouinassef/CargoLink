from django.shortcuts import render

from authentification.decorators import role_or_anonymous_required
from authentification.models import User

@role_or_anonymous_required(User.Role.PME)
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

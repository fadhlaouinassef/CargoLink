from django.contrib import messages
from django.shortcuts import redirect, render

from authentification.decorators import role_required
from authentification.models import User

@role_required(User.Role.DESTINATAIRE)
def dashboard(request):
    return render(request, 'destinataire/dashboard.html', {
        'active_tab': 'dashboard',
    })


@role_required(User.Role.DESTINATAIRE)
def suivi(request):
    return render(request, 'destinataire/suivi_livraison.html', {
        'active_tab': 'suivi',
    })


@role_required(User.Role.DESTINATAIRE)
def confirmation(request):
    if request.method == 'POST':
        messages.success(request, "Livraison #TR-8842 confirmée avec succès ! Le récépissé d'émargement a été transmis à l'expéditeur et au transporteur.")
        return redirect('destinataire:dashboard')
    return render(request, 'destinataire/confirmation_reception.html', {
        'active_tab': 'confirmation',
    })

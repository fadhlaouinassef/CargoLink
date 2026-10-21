from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from authentification.models import User

from .forms import AvisForm
from .models import Avis
from .permissions import role_required
from .services import paginer, repartition_notes


@role_required(User.Role.PME)
def avis_list(request):
    avis = request.user.avis_donnes.select_related('transporteur', 'demande')
    return render(request, 'avis_reclamations/pme/avis_list.html', {
        'active_tab': 'avis_list',
        'page': paginer(request, avis),
    })


@role_required(User.Role.PME)
@require_http_methods(['GET', 'POST'])
def avis_create(request):
    initial = {}
    if request.method == 'GET' and request.GET.get('demande', '').isdigit():
        initial['demande'] = request.GET['demande']
    form = AvisForm(request.POST if request.method == 'POST' else None, user=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error('demande', 'Vous avez déjà évalué cette demande.')
        else:
            messages.success(request, 'Merci ! Votre avis a été publié sur le profil du transporteur.')
            return redirect('pme:avis_list')
    return render(request, 'avis_reclamations/pme/avis_form.html', {
        'active_tab': 'avis_create',
        'form': form,
        'aucune_demande': not form.is_bound and not form.fields['demande'].queryset.exists(),
    })


@role_required(User.Role.TRANSPORTEUR)
def transporteur_avis(request):
    """Page « Avis & réclamations » du transporteur : ses avis publiés et les réclamations qui le visent."""
    avis_publies = Avis.objects.publies().filter(transporteur=request.user)
    reclamations = request.user.reclamations_recues.select_related('demande')
    return render(request, 'avis_reclamations/transporteur/avis.html', {
        'active_tab': 'avis',
        'stats': avis_publies.stats(),
        'repartition': repartition_notes(avis_publies),
        'page': paginer(request, avis_publies.select_related('auteur', 'demande')),
        'reclamations': reclamations[:10],
        'reclamations_total': reclamations.count(),
    })

from dataclasses import dataclass

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from authentification.models import User

from .forms import ReclamationForm
from .permissions import role_required
from .services import paginer


@dataclass(frozen=True)
class Portail:
    """Paramètres propres à chaque espace (PME ou destinataire) qui partage les mêmes vues."""
    role: str
    base_template: str
    tab_create: str
    url_create: str
    url_list: str
    url_detail: str


PORTAILS = {
    'pme': Portail(User.Role.PME, 'pme/base.html', 'reclamation_create',
                   'pme:reclamation_create', 'pme:reclamation_list', 'pme:reclamation_detail'),
    'destinataire': Portail(User.Role.DESTINATAIRE, 'destinataire/base.html', 'reclamation',
                            'destinataire:reclamation', 'destinataire:reclamation_list', 'destinataire:reclamation_detail'),
}


def _portail(request):
    portail = PORTAILS[request.resolver_match.namespace]
    if request.user.role != portail.role:
        raise PermissionDenied
    return portail


def _contexte(portail, active_tab, **extra):
    return {
        'base_template': portail.base_template,
        'active_tab': active_tab,
        'url_create': portail.url_create,
        'url_list': portail.url_list,
        'url_detail': portail.url_detail,
        **extra,
    }


@role_required(User.Role.PME, User.Role.DESTINATAIRE)
def reclamation_list(request):
    portail = _portail(request)
    reclamations = request.user.reclamations_deposees.select_related('demande', 'transporteur')
    return render(request, 'avis_reclamations/reclamation_list.html', _contexte(
        portail, 'reclamation_list', page=paginer(request, reclamations),
    ))


@role_required(User.Role.PME, User.Role.DESTINATAIRE)
@require_http_methods(['GET', 'POST'])
def reclamation_create(request):
    portail = _portail(request)
    initial = {}
    if request.method == 'GET' and request.GET.get('demande', '').isdigit():
        initial['demande'] = request.GET['demande']
    form = ReclamationForm(request.POST if request.method == 'POST' else None, user=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        reclamation = form.save()
        messages.success(
            request,
            f'Votre réclamation {reclamation.reference} a été transmise à l’administrateur CargoLink pour instruction.',
        )
        return redirect(portail.url_detail, pk=reclamation.pk)
    return render(request, 'avis_reclamations/reclamation_form.html', _contexte(
        portail, portail.tab_create,
        form=form,
        aucune_demande=not form.is_bound and not form.fields['demande'].queryset.exists(),
    ))


@role_required(User.Role.PME, User.Role.DESTINATAIRE)
def reclamation_detail(request, pk):
    portail = _portail(request)
    reclamation = get_object_or_404(
        request.user.reclamations_deposees.select_related('demande', 'transporteur', 'traitee_par'), pk=pk,
    )
    return render(request, 'avis_reclamations/reclamation_detail.html', _contexte(
        portail, 'reclamation_list', reclamation=reclamation,
    ))

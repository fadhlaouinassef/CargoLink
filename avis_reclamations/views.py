from dataclasses import dataclass

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from authentification.models import User
from authentification.views import admin_required

from .decorators import role_required
from .forms import AvisForm, ModerationAvisForm, ReclamationForm, TraitementReclamationForm
from .models import Avis, Reclamation


def _paginer(request, queryset, par_page=10):
    return Paginator(queryset, par_page).get_page(request.GET.get('page'))


def _repartition_notes(avis_publies):
    """Nombre d'avis par note (de 5 à 1), avec le pourcentage pour l'affichage des barres."""
    total = avis_publies.count()
    comptes = {note: 0 for note in range(5, 0, -1)}
    for note in avis_publies.values_list('note', flat=True):
        comptes[note] += 1
    return [
        {'note': note, 'nombre': nombre, 'pourcentage': round(nombre * 100 / total) if total else 0}
        for note, nombre in comptes.items()
    ]


# ---------------------------------------------------------------------------
# Avis : espace PME et page du transporteur
# ---------------------------------------------------------------------------

@role_required(User.Role.PME)
def avis_list(request):
    avis = request.user.avis_donnes.select_related('transporteur', 'demande')
    return render(request, 'avis_reclamations/avis_list.html', {
        'active_tab': 'avis_list',
        'page': _paginer(request, avis),
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
    return render(request, 'avis_reclamations/avis_form.html', {
        'active_tab': 'avis_create',
        'form': form,
        'aucune_demande': not form.is_bound and not form.fields['demande'].queryset.exists(),
    })


@role_required(User.Role.TRANSPORTEUR)
def transporteur_avis(request):
    """Page « Avis & réclamations » du transporteur : ses avis publiés et les réclamations qui le visent."""
    avis_publies = Avis.objects.publies().filter(transporteur=request.user)
    reclamations = request.user.reclamations_recues.select_related('demande')
    return render(request, 'avis_reclamations/transporteur_avis.html', {
        'active_tab': 'avis',
        'stats': avis_publies.stats(),
        'repartition': _repartition_notes(avis_publies),
        'page': _paginer(request, avis_publies.select_related('auteur', 'demande')),
        'reclamations': reclamations[:10],
        'reclamations_total': reclamations.count(),
    })


# ---------------------------------------------------------------------------
# Réclamations : espaces PME et destinataire (mêmes vues, paramètres propres à chaque espace)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Portail:
    role: str
    base_template: str
    tab_create: str
    url_create: str
    url_list: str
    url_detail: str
    url_update: str
    url_delete: str


PORTAILS = {
    'pme': Portail(User.Role.PME, 'pme/base.html', 'reclamation_create',
                   'pme:reclamation_create', 'pme:reclamation_list', 'pme:reclamation_detail',
                   'pme:reclamation_update', 'pme:reclamation_delete'),
    'destinataire': Portail(User.Role.DESTINATAIRE, 'destinataire/base.html', 'reclamation',
                            'destinataire:reclamation', 'destinataire:reclamation_list', 'destinataire:reclamation_detail',
                            'destinataire:reclamation_update', 'destinataire:reclamation_delete'),
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
        'url_update': portail.url_update,
        'url_delete': portail.url_delete,
        **extra,
    }


@role_required(User.Role.PME, User.Role.DESTINATAIRE)
def reclamation_list(request):
    portail = _portail(request)
    reclamations = request.user.reclamations_deposees.select_related('demande', 'transporteur')
    return render(request, 'avis_reclamations/reclamation_list.html', _contexte(
        portail, 'reclamation_list', page=_paginer(request, reclamations),
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


def _dossier_verrouille(request, portail, reclamation):
    """Réclamation déjà prise en charge ou clôturée : plus de modification ni de suppression."""
    messages.error(
        request,
        f'La réclamation {reclamation.reference} est en cours de traitement ou clôturée : '
        'elle ne peut plus être modifiée ni supprimée.',
    )
    return redirect(portail.url_detail, pk=reclamation.pk)


@role_required(User.Role.PME, User.Role.DESTINATAIRE)
@require_http_methods(['GET', 'POST'])
def reclamation_update(request, pk):
    portail = _portail(request)
    reclamation = get_object_or_404(request.user.reclamations_deposees.select_related('demande', 'transporteur'), pk=pk)
    if not reclamation.est_modifiable:
        return _dossier_verrouille(request, portail, reclamation)
    form = ReclamationForm(request.POST if request.method == 'POST' else None, instance=reclamation, user=request.user)
    if request.method == 'POST' and form.is_valid():
        champs = {nom: form.cleaned_data[nom] for nom in ('motif', 'transporteur', 'description', 'montant_prejudice')}
        # Mise à jour conditionnelle : si l'administrateur a pris le dossier en charge entre-temps, rien n'est modifié.
        modifiees = Reclamation.objects.filter(
            pk=reclamation.pk, auteur=request.user, statut=Reclamation.Statut.OUVERTE,
        ).update(**champs, updated_at=timezone.now())
        if not modifiees:
            return _dossier_verrouille(request, portail, reclamation)
        messages.success(request, f'Votre réclamation {reclamation.reference} a été modifiée.')
        return redirect(portail.url_detail, pk=reclamation.pk)
    return render(request, 'avis_reclamations/reclamation_form.html', _contexte(
        portail, 'reclamation_list', form=form, reclamation=reclamation, modification=True,
    ))


@role_required(User.Role.PME, User.Role.DESTINATAIRE)
@require_http_methods(['GET', 'POST'])
def reclamation_delete(request, pk):
    portail = _portail(request)
    reclamation = get_object_or_404(request.user.reclamations_deposees.select_related('demande'), pk=pk)
    if not reclamation.est_modifiable:
        return _dossier_verrouille(request, portail, reclamation)
    if request.method == 'POST':
        # Suppression conditionnelle : impossible si l'administrateur a pris le dossier en charge entre-temps.
        supprimees, _ = Reclamation.objects.filter(
            pk=reclamation.pk, auteur=request.user, statut=Reclamation.Statut.OUVERTE,
        ).delete()
        if not supprimees:
            return _dossier_verrouille(request, portail, reclamation)
        messages.success(request, f'La réclamation {reclamation.reference} a été supprimée.')
        return redirect(portail.url_list)
    return render(request, 'avis_reclamations/reclamation_confirm_delete.html', _contexte(
        portail, 'reclamation_list', reclamation=reclamation,
    ))


# ---------------------------------------------------------------------------
# Administration : traitement des réclamations et modération des avis
# ---------------------------------------------------------------------------

@admin_required
def admin_reclamation_list(request):
    reclamations = Reclamation.objects.select_related('auteur', 'transporteur', 'demande')
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    motif = request.GET.get('motif', '')
    if q:
        reclamations = reclamations.filter(
            Q(auteur__full_name__icontains=q) | Q(auteur__email__icontains=q)
            | Q(transporteur__full_name__icontains=q)
            | Q(demande__depart_ville__icontains=q) | Q(demande__arrivee_ville__icontains=q)
        )
    if statut in Reclamation.Statut.values:
        reclamations = reclamations.filter(statut=statut)
    if motif in Reclamation.Motif.values:
        reclamations = reclamations.filter(motif=motif)

    compteurs = dict(Reclamation.objects.values_list('statut').annotate(total=Count('pk')))
    return render(request, 'avis_reclamations/admin_reclamation_list.html', {
        'active_tab': 'reclamations',
        'page': _paginer(request, reclamations),
        'q': q,
        'statut': statut,
        'motif': motif,
        'statuts': Reclamation.Statut.choices,
        'motifs': Reclamation.Motif.choices,
        'compteurs': {valeur: compteurs.get(valeur, 0) for valeur in Reclamation.Statut.values},
        'total': sum(compteurs.values()),
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_reclamation_detail(request, pk):
    reclamation = get_object_or_404(
        Reclamation.objects.select_related('auteur', 'transporteur', 'demande', 'traitee_par'), pk=pk,
    )
    form = None
    if not reclamation.est_close:
        form = TraitementReclamationForm(
            request.POST if request.method == 'POST' else None, reclamation=reclamation,
        )
        if request.method == 'POST' and form.is_valid():
            reclamation.statut = form.cleaned_data['statut']
            reclamation.reponse_admin = form.cleaned_data['reponse']
            reclamation.traitee_par = request.user
            reclamation.traitee_le = timezone.now()
            reclamation.save()
            messages.success(
                request, f'Le dossier {reclamation.reference} est maintenant « {reclamation.get_statut_display()} ».',
            )
            return redirect('avis_admin:reclamation_detail', pk=reclamation.pk)
    elif request.method == 'POST':
        messages.error(request, 'Ce dossier est clôturé : il ne peut plus être modifié.')
        return redirect('avis_admin:reclamation_detail', pk=reclamation.pk)
    return render(request, 'avis_reclamations/admin_reclamation_detail.html', {
        'active_tab': 'reclamations',
        'reclamation': reclamation,
        'form': form,
    })


@admin_required
def admin_avis_list(request):
    avis = Avis.objects.select_related('auteur', 'transporteur', 'demande')
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    note = request.GET.get('note', '')
    if q:
        avis = avis.filter(
            Q(auteur__full_name__icontains=q) | Q(transporteur__full_name__icontains=q) | Q(commentaire__icontains=q)
        )
    if statut in Avis.Statut.values:
        avis = avis.filter(statut=statut)
    if note.isdigit() and 1 <= int(note) <= 5:
        avis = avis.filter(note=int(note))

    return render(request, 'avis_reclamations/admin_avis_list.html', {
        'active_tab': 'avis',
        'page': _paginer(request, avis),
        'q': q,
        'statut': statut,
        'note': note,
        'statuts': Avis.Statut.choices,
        'stats': Avis.objects.publies().stats(),
        'total': Avis.objects.count(),
        'masques': Avis.objects.filter(statut=Avis.Statut.MASQUE).count(),
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_avis_detail(request, pk):
    avis = get_object_or_404(Avis.objects.select_related('auteur', 'transporteur', 'demande'), pk=pk)
    form = ModerationAvisForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        if form.cleaned_data['action'] == ModerationAvisForm.ACTION_MASQUER:
            avis.statut = Avis.Statut.MASQUE
            avis.motif_moderation = form.cleaned_data['motif']
            messages.success(request, 'L’avis est masqué : il n’apparaît plus sur le profil du transporteur.')
        else:
            avis.statut = Avis.Statut.PUBLIE
            avis.motif_moderation = ''
            messages.success(request, 'L’avis est de nouveau publié.')
        avis.save()
        return redirect('avis_admin:avis_detail', pk=avis.pk)
    return render(request, 'avis_reclamations/admin_avis_detail.html', {
        'active_tab': 'avis',
        'avis': avis,
        'form': form,
    })

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from authentification.views import admin_required

from .forms import ModerationAvisForm, TraitementReclamationForm
from .models import Avis, Reclamation
from .services import paginer


@admin_required
def reclamation_list(request):
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
    return render(request, 'avis_reclamations/admin/reclamation_list.html', {
        'active_tab': 'reclamations',
        'page': paginer(request, reclamations),
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
def reclamation_detail(request, pk):
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
    return render(request, 'avis_reclamations/admin/reclamation_detail.html', {
        'active_tab': 'reclamations',
        'reclamation': reclamation,
        'form': form,
    })


@admin_required
def avis_list(request):
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

    return render(request, 'avis_reclamations/admin/avis_list.html', {
        'active_tab': 'avis',
        'page': paginer(request, avis),
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
def avis_detail(request, pk):
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
    return render(request, 'avis_reclamations/admin/avis_detail.html', {
        'active_tab': 'avis',
        'avis': avis,
        'form': form,
    })

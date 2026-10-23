import json
import logging
import time

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView
from django.views.generic.base import TemplateView

from authentification.models import User

from .forms import DisponibiliteForm, VehiculeForm
from .models import Disponibilite, Vehicule

logger = logging.getLogger(__name__)


class TransporteurRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'authentification:login'

    def test_func(self):
        return self.request.user.role == User.Role.TRANSPORTEUR

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise Http404
        return super().handle_no_permission()


class VehiculeListView(TransporteurRequiredMixin, TemplateView):
    template_name = 'transporteur/vehicules.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db.models import Prefetch
        analyses_prefetch = Prefetch(
            'analyses_risque',
            queryset=AnalyseRisque.objects.order_by('-date_analyse'),
            to_attr='analyses_recentes'
        )
        vehicles = Vehicule.objects.filter(transporteur=self.request.user).prefetch_related(analyses_prefetch)
        availabilities = Disponibilite.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')
        query = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('statut', '')
        vehicle_type = self.request.GET.get('type_vehicule', '')
        if query:
            vehicles = vehicles.filter(
                Q(immatriculation__icontains=query)
                | Q(marque__icontains=query)
                | Q(modele__icontains=query)
            )
        if status in dict(Vehicule.Statut.choices):
            vehicles = vehicles.filter(statut=status)
        if vehicle_type in dict(Vehicule.TypeVehicule.choices):
            vehicles = vehicles.filter(type_vehicule=vehicle_type)
        context.update({
            'vehicles': vehicles,
            'availabilities': availabilities,
            'vehicle_form': VehiculeForm(),
            'availability_form': DisponibiliteForm(transporteur=self.request.user),
            'query': query,
            'selected_status': status,
            'selected_type': vehicle_type,
        })
        return context


class VehiculeCreateView(TransporteurRequiredMixin, CreateView):
    model = Vehicule
    form_class = VehiculeForm
    template_name = 'transporteur/vehicules.html'
    success_url = reverse_lazy('transporteur:vehicules')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['vehicle_form'] = context.pop('form')
        context['availability_form'] = DisponibiliteForm(transporteur=self.request.user)
        context['vehicles'] = Vehicule.objects.filter(transporteur=self.request.user)
        context['availabilities'] = Disponibilite.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')
        context['query'] = context['selected_status'] = context['selected_type'] = ''
        return context

    def form_valid(self, form):
        form.instance.transporteur = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Le véhicule a été ajouté à votre flotte.')
        return response


class VehiculeUpdateView(TransporteurRequiredMixin, UpdateView):
    model = Vehicule
    form_class = VehiculeForm
    template_name = 'transporteur/vehicules.html'
    success_url = reverse_lazy('transporteur:vehicules')

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['vehicle_form'] = context.pop('form')
        context['availability_form'] = DisponibiliteForm(transporteur=self.request.user)
        context['vehicles'] = Vehicule.objects.filter(transporteur=self.request.user)
        context['availabilities'] = Disponibilite.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')
        context['editing_vehicle'] = self.object
        context['query'] = context['selected_status'] = context['selected_type'] = ''
        return context

    def form_valid(self, form):
        # Contrôle rapide : refuse le passage en maintenance si un trajet actif existe
        if form.cleaned_data.get('statut') == Vehicule.Statut.EN_MAINTENANCE and self.object.statut != Vehicule.Statut.EN_MAINTENANCE:
            from .services import verifier_passage_manuel_en_maintenance
            try:
                verifier_passage_manuel_en_maintenance(self.object)
            except ValidationError as err:
                form.add_error('statut', err.message if hasattr(err, 'message') else str(err))
                return self.form_invalid(form)
        response = super().form_valid(form)
        messages.success(self.request, 'Le véhicule a été modifié.')
        return response


class VehiculeDeleteView(TransporteurRequiredMixin, DeleteView):
    model = Vehicule
    success_url = reverse_lazy('transporteur:vehicules')
    template_name = 'transporteur/vehicule_confirm_delete.html'

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as error:
            messages.error(self.request, str(error))
            return redirect(self.success_url)
        messages.success(self.request, 'Le véhicule a été supprimé.')
        return response


class DisponibiliteCreateView(TransporteurRequiredMixin, CreateView):
    model = Disponibilite
    form_class = DisponibiliteForm
    template_name = 'transporteur/vehicules.html'
    success_url = reverse_lazy('transporteur:vehicules')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['transporteur'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['availability_form'] = context.pop('form')
        context['vehicle_form'] = VehiculeForm()
        context['vehicles'] = Vehicule.objects.filter(transporteur=self.request.user)
        context['availabilities'] = Disponibilite.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')
        context['query'] = context['selected_status'] = context['selected_type'] = ''
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La disponibilité a été enregistrée.')
        return response


class DisponibiliteUpdateView(TransporteurRequiredMixin, UpdateView):
    model = Disponibilite
    form_class = DisponibiliteForm
    template_name = 'transporteur/vehicules.html'
    success_url = reverse_lazy('transporteur:vehicules')

    def get_queryset(self):
        return Disponibilite.objects.filter(vehicule__transporteur=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['transporteur'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['availability_form'] = context.pop('form')
        context['vehicle_form'] = VehiculeForm()
        context['vehicles'] = Vehicule.objects.filter(transporteur=self.request.user)
        context['availabilities'] = Disponibilite.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')
        context['editing_availability'] = self.object
        context['query'] = context['selected_status'] = context['selected_type'] = ''
        return context

    def form_valid(self, form):
        if self.object.statut == Disponibilite.Statut.RESERVE:
            form.add_error(None, 'Une disponibilité réservée ne peut pas être modifiée.')
            return self.form_invalid(form)
        response = super().form_valid(form)
        messages.success(self.request, 'La disponibilité a été modifiée.')
        return response


class DisponibiliteDeleteView(TransporteurRequiredMixin, DeleteView):
    model = Disponibilite
    success_url = reverse_lazy('transporteur:vehicules')
    template_name = 'transporteur/disponibilite_confirm_delete.html'

    def get_queryset(self):
        return Disponibilite.objects.filter(vehicule__transporteur=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.statut == Disponibilite.Statut.RESERVE:
            messages.error(request, 'Une disponibilité réservée ne peut pas être supprimée.')
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La disponibilité a été supprimée.')
        return response


class TransporteurDisponibiliteDetailView(TransporteurRequiredMixin, DetailView):
    model = Disponibilite
    template_name = 'transporteur/disponibilite_detail.html'
    context_object_name = 'availability'

    def get_queryset(self):
        return Disponibilite.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')


class TransporteurVehiculeDetailView(TransporteurRequiredMixin, TemplateView):
    template_name = 'transporteur/vehicule_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vehicle = Vehicule.objects.filter(
            pk=self.kwargs['pk'],
            transporteur=self.request.user,
        ).first()
        if vehicle is None:
            raise Http404
        context['vehicle'] = vehicle
        context['availabilities'] = vehicle.disponibilites.all()
        context['maintenances'] = vehicle.maintenances.all()
        context['derniere_analyse'] = vehicle.analyses_risque.order_by('-date_analyse').first()
        return context


# ==============================================================================
# VUES TRANSPORTEUR : GESTION DES MAINTENANCES PLANIFIÉES
# ==============================================================================
from .forms import MaintenanceForm
from .models import Maintenance
from .services import demarrer_maintenance, terminer_maintenance, annuler_maintenance


class MaintenanceListView(TransporteurRequiredMixin, TemplateView):
    template_name = 'transporteur/maintenances.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        maintenances = Maintenance.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')

        statut = self.request.GET.get('statut', '')
        motif = self.request.GET.get('motif', '')
        vehicule_id = self.request.GET.get('vehicule', '')

        if statut in dict(Maintenance.Statut.choices):
            maintenances = maintenances.filter(statut=statut)
        if motif in dict(Maintenance.Motif.choices):
            maintenances = maintenances.filter(motif=motif)
        if vehicule_id.isdigit():
            maintenances = maintenances.filter(vehicule_id=int(vehicule_id))

        context.update({
            'maintenances': maintenances,
            'maintenance_form': MaintenanceForm(transporteur=self.request.user),
            'statuts': Maintenance.Statut.choices,
            'motifs': Maintenance.Motif.choices,
            'vehicles': Vehicule.objects.filter(transporteur=self.request.user).exclude(statut=Vehicule.Statut.DESACTIVE),
            'selected_status': statut,
            'selected_motif': motif,
            'selected_vehicle': vehicule_id,
        })
        return context


class MaintenanceDetailView(TransporteurRequiredMixin, DetailView):
    model = Maintenance
    template_name = 'transporteur/maintenance_detail.html'
    context_object_name = 'maintenance'

    def get_queryset(self):
        return Maintenance.objects.filter(
            vehicule__transporteur=self.request.user,
        ).select_related('vehicule')


class MaintenanceCreateView(TransporteurRequiredMixin, CreateView):
    model = Maintenance
    form_class = MaintenanceForm
    template_name = 'transporteur/maintenances.html'
    success_url = reverse_lazy('transporteur:maintenances')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['transporteur'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        # Détection d'avertissement : chevauchement avec disponibilités "disponible"
        m = self.object
        dispos_ouvertes = Disponibilite.objects.filter(
            vehicule=m.vehicule,
            statut=Disponibilite.Statut.DISPONIBLE,
            date_debut__lt=m.date_fin,
            date_fin__gt=m.date_debut,
        )
        if dispos_ouvertes.exists():
            messages.warning(
                self.request,
                f"La maintenance a été enregistrée. Attention : {dispos_ouvertes.count()} disponibilité(s) "
                f"ouverte(s) chevauche(nt) cette période de maintenance. Pensez à ajuster vos créneaux."
            )
        else:
            messages.success(self.request, 'La maintenance a été planifiée avec succès.')
        return response

    def form_invalid(self, form):
        # Affiche la liste des maintenances avec les erreurs du formulaire
        return MaintenanceListView.as_view()(self.request)


class MaintenanceUpdateView(TransporteurRequiredMixin, UpdateView):
    model = Maintenance
    form_class = MaintenanceForm
    template_name = 'transporteur/maintenance_form.html'
    success_url = reverse_lazy('transporteur:maintenances')

    def get_queryset(self):
        return Maintenance.objects.filter(
            vehicule__transporteur=self.request.user,
        ).exclude(statut=Maintenance.Statut.TERMINEE)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['transporteur'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La maintenance a été modifiée.')
        return response


class MaintenanceDeleteView(TransporteurRequiredMixin, DeleteView):
    model = Maintenance
    template_name = 'transporteur/maintenance_confirm_delete.html'
    success_url = reverse_lazy('transporteur:maintenances')

    def get_queryset(self):
        # Seules les maintenances planifiées peuvent être supprimées
        return Maintenance.objects.filter(
            vehicule__transporteur=self.request.user,
            statut=Maintenance.Statut.PLANIFIEE,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La maintenance a été supprimée.')
        return response


class MaintenanceDemarrerView(TransporteurRequiredMixin, View):
    def post(self, request, pk):
        maintenance = Maintenance.objects.filter(
            pk=pk, vehicule__transporteur=request.user
        ).first()
        if not maintenance:
            raise Http404
        try:
            demarrer_maintenance(maintenance)
            messages.success(request, f"La maintenance a démarré. Le véhicule {maintenance.vehicule.immatriculation} est maintenant en maintenance.")
        except ValidationError as err:
            messages.error(request, str(err.message if hasattr(err, 'message') else err))
        return redirect('transporteur:maintenances')


class MaintenanceTerminerView(TransporteurRequiredMixin, View):
    def post(self, request, pk):
        maintenance = Maintenance.objects.filter(
            pk=pk, vehicule__transporteur=request.user
        ).first()
        if not maintenance:
            raise Http404
        try:
            terminer_maintenance(maintenance)
            messages.success(request, f"La maintenance est terminée. Le véhicule {maintenance.vehicule.immatriculation} est réactivé.")
        except ValidationError as err:
            messages.error(request, str(err.message if hasattr(err, 'message') else err))
        return redirect('transporteur:maintenances')


class MaintenanceAnnulerView(TransporteurRequiredMixin, View):
    def post(self, request, pk):
        maintenance = Maintenance.objects.filter(
            pk=pk, vehicule__transporteur=request.user
        ).first()
        if not maintenance:
            raise Http404
        try:
            annuler_maintenance(maintenance)
            messages.success(request, "La maintenance a été annulée.")
        except ValidationError as err:
            messages.error(request, str(err.message if hasattr(err, 'message') else err))
        return redirect('transporteur:maintenances')


# ==============================================================================
# VUES : ANALYSE DU RISQUE DE MAINTENANCE (ASYNC + RATE-LIMITING)
# ==============================================================================
from .models import AnalyseRisque
from .services import analyser_vehicule


class AnalyserRisqueVehiculeView(TransporteurRequiredMixin, View):
    """Déclenche une analyse de risque pour un véhicule appartenant au transporteur.

    - Rate-limiting : max 10 déclenchements / minute par utilisateur (en cache).
    - Asynchrone via Celery si disponible, sinon exécution synchrone immédiate.
    - Renvoie un JSON avec task_id (ou analyse_id directement en mode synchrone).
    """

    def post(self, request, pk):
        # Vérification d'accès : le véhicule doit appartenir au transporteur
        vehicule = Vehicule.objects.filter(pk=pk, transporteur=request.user).first()
        if not vehicule:
            return JsonResponse({'error': 'Véhicule introuvable ou non autorisé.'}, status=404)

        # Rate-limiting utilisateur (10 requêtes / minute)
        cache_key = f"ia_risque_rl_{request.user.pk}"
        count = cache.get(cache_key, 0)
        if count >= 10:
            return JsonResponse(
                {'error': 'Limite de requêtes atteinte (10 par minute). Veuillez patienter.'},
                status=429,
            )
        cache.set(cache_key, count + 1, timeout=60)

        # Paramètre force pour recalculer malgré le cache hash
        force = request.POST.get('force', 'false').lower() in ('true', '1', 'yes')

        # Tentative d'exécution asynchrone Celery
        try:
            from .tasks import analyser_vehicule_task
            task = analyser_vehicule_task.delay(vehicule.pk, force=force)
            return JsonResponse({
                'status': 'started',
                'task_id': task.id,
                'vehicule_id': vehicule.pk,
            })
        except Exception as e:
            logger.info("Celery/Redis non disponible pour analyse async (%s), exécution synchrone.", e)
            # Repli synchrone gracieux si Celery ou Redis non démarré
            analyse = analyser_vehicule(vehicule.pk, force=force)
            if not analyse:
                return JsonResponse({'error': "Échec de l'analyse du risque."}, status=500)
            return JsonResponse({
                'status': 'completed',
                'analyse_id': analyse.pk,
                'niveau': analyse.niveau,
                'score': analyse.score,
                'source': analyse.source,
                'recommandation': analyse.recommandation,
                'facteurs': analyse.facteurs,
                'urgence': analyse.urgence,
                'date_analyse': analyse.date_analyse.strftime('%d/%m/%Y %H:%M'),
                'divergence': analyse.divergence,
            })


class StatutTacheRisqueView(TransporteurRequiredMixin, View):
    """Interroge l'état d'une tâche d'analyse Celery (polling court)."""

    def get(self, request, task_id):
        try:
            from celery.result import AsyncResult
            res = AsyncResult(task_id)
            state = res.state
            if state == 'SUCCESS':
                data = res.result or {}
                analyse_id = data.get('analyse_id')
                analyse = AnalyseRisque.objects.filter(pk=analyse_id).first() if analyse_id else None
                if analyse:
                    return JsonResponse({
                        'status': 'completed',
                        'analyse_id': analyse.pk,
                        'niveau': analyse.niveau,
                        'score': analyse.score,
                        'source': analyse.source,
                        'recommandation': analyse.recommandation,
                        'facteurs': analyse.facteurs,
                        'urgence': analyse.urgence,
                        'date_analyse': analyse.date_analyse.strftime('%d/%m/%Y %H:%M'),
                        'divergence': analyse.divergence,
                    })
                return JsonResponse({'status': 'completed', 'data': data})
            elif state in ('FAILURE', 'REVOKED'):
                return JsonResponse({'status': 'failed', 'error': "L'analyse a échoué."}, status=500)
            else:
                return JsonResponse({'status': 'pending', 'state': state})
        except Exception as e:
            logger.warning("Erreur interrogation statut Celery (%s).", e)
            return JsonResponse({'status': 'unknown', 'error': str(e)}, status=200)



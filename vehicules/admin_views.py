from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from authentification.models import User

from .forms import AdminVehiculeForm, DisponibiliteForm
from .models import Disponibilite, Vehicule


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'authentification:login'

    def test_func(self):
        return self.request.user.role == User.Role.ADMIN

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise Http404
        return super().handle_no_permission()


class AdminVehiculeListView(AdminRequiredMixin, ListView):
    model = Vehicule
    template_name = 'dashboard/vehicles.html'
    context_object_name = 'vehicles'
    paginate_by = 12

    def get_queryset(self):
        queryset = Vehicule.objects.select_related('transporteur')
        query = self.request.GET.get('q', '').strip()
        owner = self.request.GET.get('transporteur', '')
        status = self.request.GET.get('statut', '')
        vehicle_type = self.request.GET.get('type_vehicule', '')
        if query:
            queryset = queryset.filter(
                Q(immatriculation__icontains=query)
                | Q(marque__icontains=query)
                | Q(modele__icontains=query)
                | Q(transporteur__full_name__icontains=query)
                | Q(transporteur__email__icontains=query)
            )
        if owner.isdigit():
            queryset = queryset.filter(transporteur_id=owner)
        if status in dict(Vehicule.Statut.choices):
            queryset = queryset.filter(statut=status)
        if vehicle_type in dict(Vehicule.TypeVehicule.choices):
            queryset = queryset.filter(type_vehicule=vehicle_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_vehicles = Vehicule.objects.all()
        context.update({
            'total_vehicles': all_vehicles.count(),
            'active_vehicles': all_vehicles.filter(statut=Vehicule.Statut.ACTIF).count(),
            'maintenance_vehicles': all_vehicles.filter(statut=Vehicule.Statut.EN_MAINTENANCE).count(),
            'disabled_vehicles': all_vehicles.filter(statut=Vehicule.Statut.DESACTIVE).count(),
            'transporteurs': User.objects.filter(role=User.Role.TRANSPORTEUR).order_by('full_name'),
            'vehicle_types': Vehicule.TypeVehicule.choices,
            'vehicle_statuses': Vehicule.Statut.choices,
            'query': self.request.GET.get('q', ''),
            'selected_owner': self.request.GET.get('transporteur', ''),
            'selected_status': self.request.GET.get('statut', ''),
            'selected_type': self.request.GET.get('type_vehicule', ''),
        })
        return context


class AdminVehiculeDetailView(AdminRequiredMixin, DetailView):
    model = Vehicule
    template_name = 'dashboard/vehicle-detail.html'
    context_object_name = 'vehicle'

    def get_queryset(self):
        return Vehicule.objects.select_related('transporteur').prefetch_related('disponibilites')


class AdminVehiculeCreateView(AdminRequiredMixin, CreateView):
    model = Vehicule
    form_class = AdminVehiculeForm
    template_name = 'dashboard/vehicle-form.html'
    success_url = reverse_lazy('authentification:admin_vehicles')

    def form_valid(self, form):
        messages.success(self.request, 'Le véhicule a été créé.')
        return super().form_valid(form)


class AdminVehiculeUpdateView(AdminRequiredMixin, UpdateView):
    model = Vehicule
    form_class = AdminVehiculeForm
    template_name = 'dashboard/vehicle-form.html'
    success_url = reverse_lazy('authentification:admin_vehicles')

    def form_valid(self, form):
        messages.success(self.request, 'Le véhicule a été modifié.')
        return super().form_valid(form)


class AdminVehiculeDeleteView(AdminRequiredMixin, DeleteView):
    model = Vehicule
    template_name = 'dashboard/vehicle-delete.html'
    success_url = reverse_lazy('authentification:admin_vehicles')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as error:
            messages.error(self.request, str(error))
            return redirect('authentification:admin_vehicle_detail', self.object.pk)
        messages.success(self.request, 'Le véhicule a été supprimé.')
        return response


class AdminDisponibiliteCreateView(AdminRequiredMixin, CreateView):
    model = Disponibilite
    form_class = DisponibiliteForm
    template_name = 'dashboard/vehicle-form.html'
    success_url = reverse_lazy('authentification:admin_vehicles')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['transporteur'] = None
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'La disponibilité a été créée.')
        return super().form_valid(form)


class AdminDisponibiliteUpdateView(AdminRequiredMixin, UpdateView):
    model = Disponibilite
    form_class = DisponibiliteForm
    template_name = 'dashboard/vehicle-form.html'
    success_url = reverse_lazy('authentification:admin_vehicles')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['transporteur'] = None
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'La disponibilité a été modifiée.')
        return super().form_valid(form)


class AdminDisponibiliteDetailView(AdminRequiredMixin, DetailView):
    model = Disponibilite
    template_name = 'dashboard/availability-detail.html'
    context_object_name = 'availability'


class AdminDisponibiliteDeleteView(AdminRequiredMixin, DeleteView):
    model = Disponibilite
    template_name = 'dashboard/vehicle-delete.html'
    success_url = reverse_lazy('authentification:admin_vehicles')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La disponibilité a été supprimée.')
        return response

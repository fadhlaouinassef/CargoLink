from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView
from django.views.generic.base import TemplateView

from authentification.models import User

from .forms import DisponibiliteForm, VehiculeForm
from .models import Disponibilite, Vehicule


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
        vehicles = Vehicule.objects.filter(transporteur=self.request.user)
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
        return context

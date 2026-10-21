from django.urls import path
from django.views.generic import TemplateView

from gestion_trajets.decorators import transporteur_required
from gestion_trajets.urls import urlpatterns as module_urls

app_name = 'transporteur'

urlpatterns = module_urls + [
    path(route, transporteur_required(TemplateView.as_view(
        template_name=f'transporteur/{name}.html', extra_context={'active_tab': name}
    )), name=name)
    for route, name in [('', 'dashboard'), ('vehicules/', 'vehicules'), ('avis/', 'avis')]
from vehicules.views import (
    DisponibiliteCreateView,
    DisponibiliteDeleteView,
    DisponibiliteUpdateView,
    VehiculeCreateView,
    VehiculeDeleteView,
    VehiculeListView,
    VehiculeUpdateView,
    TransporteurDisponibiliteDetailView,
    TransporteurVehiculeDetailView,
)
from demandes import views as demande_views

app_name = 'transporteur'

urlpatterns = [
    path('', TemplateView.as_view(template_name='transporteur/dashboard.html', extra_context={'active_tab': 'dashboard'}), name='dashboard'),
    path('trajets/', TemplateView.as_view(template_name='transporteur/trajets.html', extra_context={'active_tab': 'trajets'}), name='trajets'),
    path('demandes/', TemplateView.as_view(template_name='transporteur/demandes.html', extra_context={'active_tab': 'demandes'}), name='demandes'),
    path('offres/', TemplateView.as_view(template_name='transporteur/offres.html', extra_context={'active_tab': 'offres'}), name='offres'),
    path('vehicules/', VehiculeListView.as_view(), name='vehicules'),
    path('vehicules/nouveau/', VehiculeCreateView.as_view(), name='vehicule_create'),
    path('vehicules/<int:pk>/modifier/', VehiculeUpdateView.as_view(), name='vehicule_update'),
    path('vehicules/<int:pk>/', TransporteurVehiculeDetailView.as_view(), name='vehicule_detail'),
    path('vehicules/<int:pk>/supprimer/', VehiculeDeleteView.as_view(), name='vehicule_delete'),
    path('disponibilites/nouvelle/', DisponibiliteCreateView.as_view(), name='disponibilite_create'),
    path('disponibilites/<int:pk>/modifier/', DisponibiliteUpdateView.as_view(), name='disponibilite_update'),
    path('disponibilites/<int:pk>/', TransporteurDisponibiliteDetailView.as_view(), name='disponibilite_detail'),
    path('disponibilites/<int:pk>/supprimer/', DisponibiliteDeleteView.as_view(), name='disponibilite_delete'),
    path('transports/', TemplateView.as_view(template_name='transporteur/transports.html', extra_context={'active_tab': 'transports'}), name='transports'),
    path('avis/', TemplateView.as_view(template_name='transporteur/avis.html', extra_context={'active_tab': 'avis'}), name='avis'),
    path('demandes/', demande_views.transporteur_demandes, name='demandes'),
    path('demandes/<int:pk>/', demande_views.transporteur_demande_detail, name='demande_detail'),
] + [
    path(route, TemplateView.as_view(template_name=f'transporteur/{name}.html', extra_context={'active_tab': name}), name=name)
    for route, name in [('', 'dashboard'), ('trajets/', 'trajets'), ('offres/', 'offres'), ('vehicules/', 'vehicules'), ('transports/', 'transports'), ('avis/', 'avis')]
]

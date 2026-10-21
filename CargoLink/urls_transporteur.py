from django.urls import path
from django.views.generic import TemplateView

from gestion_trajets.decorators import transporteur_required
from gestion_trajets.urls import urlpatterns as trajet_urls
from vehicules.views import (
    DisponibiliteCreateView,
    DisponibiliteDeleteView,
    DisponibiliteUpdateView,
    TransporteurDisponibiliteDetailView,
    TransporteurVehiculeDetailView,
    VehiculeCreateView,
    VehiculeDeleteView,
    VehiculeListView,
    VehiculeUpdateView,
)

app_name = 'transporteur'

urlpatterns = trajet_urls + [
    path(
        '',
        transporteur_required(TemplateView.as_view(
            template_name='transporteur/dashboard.html',
            extra_context={'active_tab': 'dashboard'},
        )),
        name='dashboard',
    ),
    path('vehicules/', VehiculeListView.as_view(), name='vehicules'),
    path('vehicules/nouveau/', VehiculeCreateView.as_view(), name='vehicule_create'),
    path('vehicules/<int:pk>/modifier/', VehiculeUpdateView.as_view(), name='vehicule_update'),
    path('vehicules/<int:pk>/', TransporteurVehiculeDetailView.as_view(), name='vehicule_detail'),
    path('vehicules/<int:pk>/supprimer/', VehiculeDeleteView.as_view(), name='vehicule_delete'),
    path('disponibilites/nouvelle/', DisponibiliteCreateView.as_view(), name='disponibilite_create'),
    path('disponibilites/<int:pk>/modifier/', DisponibiliteUpdateView.as_view(), name='disponibilite_update'),
    path('disponibilites/<int:pk>/', TransporteurDisponibiliteDetailView.as_view(), name='disponibilite_detail'),
    path('disponibilites/<int:pk>/supprimer/', DisponibiliteDeleteView.as_view(), name='disponibilite_delete'),
    path(
        'avis/',
        transporteur_required(TemplateView.as_view(
            template_name='transporteur/avis.html',
            extra_context={'active_tab': 'avis'},
        )),
        name='avis',
    ),
]

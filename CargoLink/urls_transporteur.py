from django.urls import path
from django.views.generic import TemplateView

from avis_reclamations.urls import transporteur_urls
from gestion_trajets_offres.decorators import transporteur_required
from gestion_trajets_offres.urls import urlpatterns as trajet_urls
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
from vehicules.ia_views import AssistantDisponibiliteIAView
from suivi_transport import views as suivi_views

app_name = 'transporteur'

urlpatterns = [
    path('transports/', suivi_views.transporteur_list, name='transports'),
    path('transports/<int:pk>/', suivi_views.transporteur_detail, name='transport_detail'),
    path('transports/<int:pk>/evenement/', suivi_views.ajouter_evenement, name='transport_evenement'),
    path('transports/<int:pk>/evenement/<int:event_pk>/modifier/', suivi_views.modifier_evenement, name='transport_evenement_edit'),
    path('transports/<int:pk>/evenement/<int:event_pk>/supprimer/', suivi_views.supprimer_evenement, name='transport_evenement_delete'),
    path('transports/<int:pk>/supprimer/', suivi_views.supprimer_transport, name='transport_delete'),
] + [url for url in trajet_urls if url.name != 'transports'] + [
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
    path('disponibilites/ia-assistant/', AssistantDisponibiliteIAView.as_view(), name='disponibilite_ia_assistant'),
    *transporteur_urls,
]

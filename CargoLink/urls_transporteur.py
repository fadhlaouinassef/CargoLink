from django.urls import path
from django.views.generic import TemplateView

from avis_reclamations.urls import transporteur_urls
from gestion_trajets_offres.decorators import transporteur_required
from gestion_trajets_offres.urls import urlpatterns as trajet_urls
from vehicules.views import (
    DisponibiliteCreateView,
    DisponibiliteDeleteView,
    DisponibiliteUpdateView,
    MaintenanceAnnulerView,
    MaintenanceCreateView,
    MaintenanceDeleteView,
    MaintenanceDemarrerView,
    MaintenanceDetailView,
    MaintenanceListView,
    MaintenanceTerminerView,
    MaintenanceUpdateView,
    TransporteurDisponibiliteDetailView,
    TransporteurVehiculeDetailView,
    VehiculeCreateView,
    VehiculeDeleteView,
    VehiculeListView,
    VehiculeUpdateView,
    AnalyserRisqueVehiculeView,
    StatutTacheRisqueView,
)
from vehicules.ia_views import AssistantDisponibiliteIAView

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
    path('vehicules/<int:pk>/analyser-risque/', AnalyserRisqueVehiculeView.as_view(), name='vehicule_analyser_risque'),
    path('taches/risque/<str:task_id>/statut/', StatutTacheRisqueView.as_view(), name='tache_risque_statut'),
    path('disponibilites/nouvelle/', DisponibiliteCreateView.as_view(), name='disponibilite_create'),
    path('disponibilites/<int:pk>/modifier/', DisponibiliteUpdateView.as_view(), name='disponibilite_update'),
    path('disponibilites/<int:pk>/', TransporteurDisponibiliteDetailView.as_view(), name='disponibilite_detail'),
    path('disponibilites/<int:pk>/supprimer/', DisponibiliteDeleteView.as_view(), name='disponibilite_delete'),
    path('disponibilites/ia-assistant/', AssistantDisponibiliteIAView.as_view(), name='disponibilite_ia_assistant'),
    path('maintenances/', MaintenanceListView.as_view(), name='maintenances'),
    path('maintenances/nouvelle/', MaintenanceCreateView.as_view(), name='maintenance_create'),
    path('maintenances/<int:pk>/', MaintenanceDetailView.as_view(), name='maintenance_detail'),
    path('maintenances/<int:pk>/modifier/', MaintenanceUpdateView.as_view(), name='maintenance_update'),
    path('maintenances/<int:pk>/supprimer/', MaintenanceDeleteView.as_view(), name='maintenance_delete'),
    path('maintenances/<int:pk>/demarrer/', MaintenanceDemarrerView.as_view(), name='maintenance_demarrer'),
    path('maintenances/<int:pk>/terminer/', MaintenanceTerminerView.as_view(), name='maintenance_terminer'),
    path('maintenances/<int:pk>/annuler/', MaintenanceAnnulerView.as_view(), name='maintenance_annuler'),
    *transporteur_urls,
]

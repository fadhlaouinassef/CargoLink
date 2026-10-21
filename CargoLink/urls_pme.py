from django.urls import path
from . import views_pme

app_name = 'pme'

urlpatterns = [
    path('', views_pme.dashboard, name='dashboard'),
    path('demandes/', views_pme.demandes_list, name='demandes_list'),
    path('demandes/nouvelle/', views_pme.demande_create, name='demande_create'),
    path('demandes/detail/', views_pme.demande_detail, name='demande_detail'),
    path('offres/comparer/', views_pme.offres_comparer, name='offres_comparer'),
    path('transports/', views_pme.transports_list, name='transports_list'),
    path('transports/suivi/', views_pme.transport_suivi, name='transport_suivi'),
    path('avis/nouveau/', views_pme.avis_create, name='avis_create'),
    path('reclamations/nouvelle/', views_pme.reclamation_create, name='reclamation_create'),
]

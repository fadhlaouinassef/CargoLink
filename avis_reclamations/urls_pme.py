from django.urls import path

from . import views_avis, views_reclamation

# Inclus dans CargoLink/urls_pme.py (espace de noms « pme »).
urlpatterns = [
    path('avis/', views_avis.avis_list, name='avis_list'),
    path('avis/nouveau/', views_avis.avis_create, name='avis_create'),
    path('reclamations/', views_reclamation.reclamation_list, name='reclamation_list'),
    path('reclamations/nouvelle/', views_reclamation.reclamation_create, name='reclamation_create'),
    path('reclamations/<int:pk>/', views_reclamation.reclamation_detail, name='reclamation_detail'),
]

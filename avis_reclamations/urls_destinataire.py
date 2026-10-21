from django.urls import path

from . import views_reclamation

# Inclus dans CargoLink/urls_destinataire.py (espace de noms « destinataire »).
urlpatterns = [
    path('reclamation/', views_reclamation.reclamation_create, name='reclamation'),
    path('reclamations/', views_reclamation.reclamation_list, name='reclamation_list'),
    path('reclamations/<int:pk>/', views_reclamation.reclamation_detail, name='reclamation_detail'),
]

from django.urls import path

from avis_reclamations.urls import destinataire_urls
from . import views_destinataire

app_name = 'destinataire'

urlpatterns = [
    path('', views_destinataire.dashboard, name='dashboard'),
    path('suivi/', views_destinataire.suivi, name='suivi'),
    path('confirmation/', views_destinataire.confirmation, name='confirmation'),
    *destinataire_urls,
]

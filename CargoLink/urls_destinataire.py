from django.urls import include, path
from . import views_destinataire

app_name = 'destinataire'

urlpatterns = [
    path('', views_destinataire.dashboard, name='dashboard'),
    path('suivi/', views_destinataire.suivi, name='suivi'),
    path('confirmation/', views_destinataire.confirmation, name='confirmation'),
    path('', include('avis_reclamations.urls_destinataire')),
]

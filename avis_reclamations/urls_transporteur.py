from django.urls import path

from . import views_avis

# Inclus dans CargoLink/urls_transporteur.py (espace de noms « transporteur »).
urlpatterns = [
    path('avis/', views_avis.transporteur_avis, name='avis'),
]

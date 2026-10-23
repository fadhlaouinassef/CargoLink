from django.urls import path

from . import views

# Routes ajoutées à l'espace PME (voir CargoLink/urls_pme.py, espace de noms « pme »).
pme_urls = [
    path('demandes/<int:pk>/offres/classement/', views.offres_classees, name='offres_classees'),
]

from django.urls import path

from . import views

# Routes de l'espace administrateur, montées sous /dashboard/ (voir CargoLink/urls.py).
app_name = 'avis_admin'

urlpatterns = [
    path('reclamations/', views.admin_reclamation_list, name='reclamation_list'),
    path('reclamations/<int:pk>/', views.admin_reclamation_detail, name='reclamation_detail'),
    path('avis/', views.admin_avis_list, name='avis_list'),
    path('avis/<int:pk>/', views.admin_avis_detail, name='avis_detail'),
]

# Routes ajoutées aux espaces des acteurs (voir CargoLink/urls_pme.py, urls_destinataire.py, urls_transporteur.py).
pme_urls = [
    path('avis/', views.avis_list, name='avis_list'),
    path('avis/nouveau/', views.avis_create, name='avis_create'),
    path('reclamations/', views.reclamation_list, name='reclamation_list'),
    path('reclamations/nouvelle/', views.reclamation_create, name='reclamation_create'),
    path('reclamations/<int:pk>/', views.reclamation_detail, name='reclamation_detail'),
    path('reclamations/<int:pk>/modifier/', views.reclamation_update, name='reclamation_update'),
    path('reclamations/<int:pk>/supprimer/', views.reclamation_delete, name='reclamation_delete'),
]

destinataire_urls = [
    path('reclamation/', views.reclamation_create, name='reclamation'),
    path('reclamations/', views.reclamation_list, name='reclamation_list'),
    path('reclamations/<int:pk>/', views.reclamation_detail, name='reclamation_detail'),
    path('reclamations/<int:pk>/modifier/', views.reclamation_update, name='reclamation_update'),
    path('reclamations/<int:pk>/supprimer/', views.reclamation_delete, name='reclamation_delete'),
]

transporteur_urls = [
    path('avis/', views.transporteur_avis, name='avis'),
]

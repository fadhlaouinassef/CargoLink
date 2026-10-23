from django.urls import path

from . import views

app_name = 'gestion_trajets_offres'

urlpatterns = [
    path('demandes/', views.demandes, name='demandes'),
    path('demandes/<int:pk>/', views.demande_detail, name='demande_detail'),
    path('demandes/<int:demande_pk>/postuler/', views.offre_form, name='offre_create'),
    path('trajets/', views.trajets, name='trajets'),
    path('trajets/ajouter/', views.trajet_form, name='trajet_create'),
    path('trajets/<int:pk>/rapport/', views.rapport_trajet, name='trajet_rapport'),
    path('trajets/<int:pk>/modifier/', views.trajet_form, name='trajet_update'),
    path('trajets/<int:pk>/supprimer/', views.supprimer, {'kind': 'trajet'}, name='trajet_delete'),
    path('transports/', views.transports, name='transports'),
    path('trajets/<int:pk>/suivi/', views.suivi_form, name='trajet_suivi'),
    path('offres/', views.offres, name='offres'),
    path('offres/<int:pk>/modifier/', views.offre_form, name='offre_update'),
    path('offres/<int:pk>/supprimer/', views.supprimer, {'kind': 'offre'}, name='offre_delete'),
]

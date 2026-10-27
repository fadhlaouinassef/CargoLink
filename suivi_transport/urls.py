from django.urls import path

from . import views

app_name = 'suivi_transport'

urlpatterns = [
    path('pme/', views.pme_list, name='pme_list'),
    path('pme/<int:pk>/', views.pme_detail, name='pme_detail'),
    path('pme/<int:pk>/confirmer/', views.confirmer_reception, name='confirmer_reception'),
    path('transporteur/', views.transporteur_list, name='transporteur_list'),
    path('transporteur/geocodage-inverse/', views.transporteur_reverse_geocode, name='transporteur_reverse_geocode'),
    path('transporteur/<int:pk>/', views.transporteur_detail, name='transporteur_detail'),
    path('transporteur/<int:pk>/evenement/', views.ajouter_evenement, name='ajouter_evenement'),
    path('transporteur/<int:pk>/supprimer/', views.supprimer_transport, name='supprimer_transport'),
]

from django.urls import include, path
from avis_reclamations.urls import pme_urls
from demandes.views import dashboard, demande_detail
from . import views_pme

app_name = 'pme'

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('demandes/detail/', demande_detail, name='demande_detail'),
    path('demandes/', include('demandes.urls')),
    path('offres/comparer/', views_pme.offres_comparer, name='offres_comparer'),
    path('transports/', views_pme.transports_list, name='transports_list'),
    path('transports/suivi/', views_pme.transport_suivi, name='transport_suivi'),
    *pme_urls,
]

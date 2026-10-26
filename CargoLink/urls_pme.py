from django.urls import include, path
from avis_reclamations.urls import pme_urls
from matching_des_offres.urls import pme_urls as matching_urls
from demandes.views import dashboard, demande_detail
from . import views_pme
from suivi_transport import views as suivi_views

app_name = 'pme'

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('demandes/detail/', demande_detail, name='demande_detail'),
    path('demandes/', include('demandes.urls')),
    path('offres/comparer/', views_pme.offres_comparer, name='offres_comparer'),
    path('transports/', suivi_views.pme_list, name='transports_list'),
    path('transports/suivi/', suivi_views.pme_list, name='transport_suivi'),
    path('transports/<int:pk>/', suivi_views.pme_detail, name='transport_detail'),
    path('transports/<int:pk>/offres/<int:offre_pk>/accepter-remplacement/', suivi_views.accepter_offre_remplacement, name='accepter_offre_remplacement'),
    path('transports/<int:pk>/confirmer/', suivi_views.confirmer_reception, name='confirmer_reception'),
    *pme_urls,
    *matching_urls,
]

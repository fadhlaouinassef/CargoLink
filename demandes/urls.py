from django.urls import path

from . import views
from gestion_trajets_offres.views import accepter_offre, demande_offres

urlpatterns = [
    path('', views.demandes_list, name='demandes_list'),
    path('nouvelle/', views.demande_create, name='demande_create'),
    path('ameliorer-description/', views.ai_improve_description, name='ai_improve_description'),
    path('<int:pk>/modifier/', views.demande_update, name='demande_update'),
    path('<int:pk>/supprimer/', views.demande_delete, name='demande_delete'),
    path('<int:pk>/offres/', demande_offres, name='demande_offres'),
    path('<int:pk>/offres/<int:offre_pk>/accepter/', accepter_offre, name='accepter_offre'),
    path('<int:pk>/', views.demande_detail, name='demande_detail_item'),
]

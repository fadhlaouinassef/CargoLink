from django.urls import path

from . import views_admin

app_name = 'avis_admin'

urlpatterns = [
    path('reclamations/', views_admin.reclamation_list, name='reclamation_list'),
    path('reclamations/<int:pk>/', views_admin.reclamation_detail, name='reclamation_detail'),
    path('avis/', views_admin.avis_list, name='avis_list'),
    path('avis/<int:pk>/', views_admin.avis_detail, name='avis_detail'),
]

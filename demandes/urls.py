from django.urls import path

from . import views

urlpatterns = [
    path('', views.demandes_list, name='demandes_list'),
    path('nouvelle/', views.demande_create, name='demande_create'),
    path('<int:pk>/', views.demande_detail, name='demande_detail_item'),
]

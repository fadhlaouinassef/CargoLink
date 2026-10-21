from django.urls import path

from .forms import LoginForm
from . import views
from vehicules.admin_views import (
    AdminDisponibiliteCreateView,
    AdminDisponibiliteDeleteView,
    AdminDisponibiliteUpdateView,
    AdminDisponibiliteDetailView,
    AdminVehiculeCreateView,
    AdminVehiculeDeleteView,
    AdminVehiculeDetailView,
    AdminVehiculeListView,
    AdminVehiculeUpdateView,
)

app_name = 'authentification'

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/users/create/', views.admin_user_create, name='admin_user_create'),
    path('dashboard/users/<int:pk>/', views.admin_user_detail, name='admin_user_detail'),
    path('dashboard/users/<int:pk>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('dashboard/users/<int:pk>/delete/', views.admin_user_delete, name='admin_user_delete'),
    path('dashboard/users/<int:pk>/toggle-active/', views.admin_user_toggle_active, name='admin_user_toggle_active'),
    path('dashboard/vehicules/', AdminVehiculeListView.as_view(), name='admin_vehicles'),
    path('dashboard/vehicules/nouveau/', AdminVehiculeCreateView.as_view(), name='admin_vehicle_create'),
    path('dashboard/vehicules/<int:pk>/', AdminVehiculeDetailView.as_view(), name='admin_vehicle_detail'),
    path('dashboard/vehicules/<int:pk>/modifier/', AdminVehiculeUpdateView.as_view(), name='admin_vehicle_update'),
    path('dashboard/vehicules/<int:pk>/supprimer/', AdminVehiculeDeleteView.as_view(), name='admin_vehicle_delete'),
    path('dashboard/disponibilites/nouvelle/', AdminDisponibiliteCreateView.as_view(), name='admin_availability_create'),
    path('dashboard/disponibilites/<int:pk>/modifier/', AdminDisponibiliteUpdateView.as_view(), name='admin_availability_update'),
    path('dashboard/disponibilites/<int:pk>/', AdminDisponibiliteDetailView.as_view(), name='admin_availability_detail'),
    path('dashboard/disponibilites/<int:pk>/supprimer/', AdminDisponibiliteDeleteView.as_view(), name='admin_availability_delete'),
    path(
        'signin/',
        views.RoleBasedLoginView.as_view(
            authentication_form=LoginForm,
            next_page='home',
            template_name='authentification/login.html',
        ),
        name='login',
    ),
    path('register/', views.register, name='register'),
    path('forget-password/', views.forget_password, name='forget_password'),
    path('forget-password/verify/', views.verify_code, name='verify_code'),
    path('forget-password/reset/', views.reset_password, name='reset_password'),
]

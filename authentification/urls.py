from django.contrib.auth.views import LoginView
from django.urls import path

from .forms import LoginForm
from . import views

app_name = 'authentification'

urlpatterns = [
    path(
        'signin/',
        LoginView.as_view(
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

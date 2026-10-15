from django.contrib.auth.views import LoginView
from django.urls import path

from . import views

app_name = 'authentification'

urlpatterns = [
    path('signin/', LoginView.as_view(template_name='authentification/login.html'), name='login'),
    path('register/', views.register, name='register'),
    path('forget-password/', views.forget_password, name='forget_password'),
]

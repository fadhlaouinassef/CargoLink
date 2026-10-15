from django.contrib.auth.views import LoginView
from django.urls import path

app_name = 'signin'

urlpatterns = [
    path('', LoginView.as_view(template_name='signin/login.html'), name='login'),
]
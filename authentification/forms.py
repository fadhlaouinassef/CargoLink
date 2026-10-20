from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['full_name', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return email

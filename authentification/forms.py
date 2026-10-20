from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class LoginForm(AuthenticationForm):
    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['full_name', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return email


class AdminUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['full_name', 'email', 'role', 'is_active']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return email


class AdminUserChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['full_name', 'email', 'role', 'is_active']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return email


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        error_messages={
            'required': 'Saisissez votre adresse e-mail.',
            'invalid': 'Saisissez une adresse e-mail valide.',
        },
    )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class VerifyCodeForm(forms.Form):
    code = forms.CharField(
        max_length=10,
        error_messages={'required': 'Saisissez le code reçu par e-mail.'},
    )

    def clean_code(self):
        code = self.cleaned_data['code'].replace(' ', '')
        if len(code) != 6 or not code.isdigit():
            raise forms.ValidationError('Le code doit contenir exactement 6 chiffres.')
        return code

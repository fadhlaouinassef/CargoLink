from django.shortcuts import render


def register(request):
    return render(request, 'authentification/register.html')


def forget_password(request):
    return render(request, 'authentification/forget-password.html')

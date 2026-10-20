from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import SignupForm


@require_http_methods(['GET', 'POST'])
def register(request):
    form = SignupForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error(None, 'Impossible de créer ce compte. Vérifiez vos informations.')
        else:
            return redirect('authentification:login')
    return render(request, 'authentification/register.html', {'form': form})


def forget_password(request):
    return render(request, 'authentification/forget-password.html')

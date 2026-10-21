from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def transporteur_required(view):
    @login_required(login_url='authentification:login')
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != 'transporteur':
            return HttpResponseForbidden('Cet espace est réservé aux transporteurs.')
        return view(request, *args, **kwargs)
    return wrapped

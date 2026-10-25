from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Exige un compte connecté appartenant à l'un des rôles indiqués."""
    def decorator(view):
        @wraps(view)
        @login_required(login_url='authentification:login')
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def role_or_anonymous_required(*roles):
    """Autorise un visiteur anonyme, mais interdit aux comptes d'un autre rôle l'accès à cette vue."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

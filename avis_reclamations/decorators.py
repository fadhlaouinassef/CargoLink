from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Exige un utilisateur connecté dont le rôle fait partie de `roles` (sinon 403)."""
    def decorator(view):
        @wraps(view)
        @login_required(login_url='authentification:login')
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

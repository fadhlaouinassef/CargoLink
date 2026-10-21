import smtplib
import time

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .forms import (
    AdminUserChangeForm,
    AdminUserCreationForm,
    ForgotPasswordForm,
    SignupForm,
    VerifyCodeForm,
)
from .models import PasswordResetCode, User

RESEND_DELAY = 60  # secondes entre deux envois de code
VERIFIED_LIFETIME = 15 * 60  # secondes pour choisir le nouveau mot de passe après vérification


class RoleBasedLoginView(LoginView):
    def get_success_url(self):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return reverse('authentification:admin_dashboard')
        elif user.role == User.Role.PME:
            return reverse('pme:dashboard')
        elif user.role == User.Role.DESTINATAIRE:
            return reverse('destinataire:dashboard')
        return super().get_success_url()


def admin_required(view):
    @login_required(login_url='authentification:login')
    def wrapped(request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def _user_form_context(form, title, submit_label):
    return {'form': form, 'title': title, 'submit_label': submit_label}


@admin_required
def admin_dashboard(request):
    users = User.objects.all().order_by('-date_joined')
    query = request.GET.get('q', '').strip()
    role = request.GET.get('role', '')
    status = request.GET.get('status', '')
    if query:
        users = users.filter(Q(full_name__icontains=query) | Q(email__icontains=query))
    if role in dict(User.Role.choices):
        users = users.filter(role=role)
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    all_users = User.objects.all()
    context = {
        'users': users,
        'create_form': AdminUserCreationForm(),
        'query': query,
        'selected_role': role,
        'selected_status': status,
        'role_choices': User.Role.choices,
        'total_users': all_users.count(),
        'new_users': all_users.filter(date_joined__gte=month_start).count(),
        'active_users': all_users.filter(is_active=True).count(),
        'inactive_users': all_users.filter(is_active=False).count(),
    }
    return render(request, 'dashboard/admin-dashboard.html', context)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_user_create(request):
    form = AdminUserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Le compte utilisateur a été créé.')
        return redirect('authentification:admin_dashboard')
    return render(request, 'dashboard/user-form.html', _user_form_context(
        form, 'Ajouter un compte utilisateur', 'Créer le compte',
    ))


@admin_required
def admin_user_detail(request, pk):
    user = get_object_or_404(User, pk=pk)
    return render(request, 'dashboard/user-detail.html', {'managed_user': user})


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminUserChangeForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        if user.pk == request.user.pk and not form.cleaned_data['is_active']:
            form.add_error('is_active', 'Vous ne pouvez pas désactiver votre propre compte.')
        else:
            form.save()
            messages.success(request, 'Le compte utilisateur a été modifié.')
            return redirect('authentification:admin_user_detail', pk=user.pk)
    return render(request, 'dashboard/user-form.html', _user_form_context(
        form, 'Modifier le compte utilisateur', 'Enregistrer les modifications',
    ))


@admin_required
@require_http_methods(['POST'])
def admin_user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, 'Vous ne pouvez pas supprimer votre propre compte.')
    else:
        user.delete()
        messages.success(request, 'Le compte utilisateur a été supprimé.')
    return redirect('authentification:admin_dashboard')


@admin_required
@require_http_methods(['POST'])
def admin_user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, 'Vous ne pouvez pas désactiver votre propre compte.')
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        state = 'activé' if user.is_active else 'désactivé'
        messages.success(request, f'Le compte utilisateur a été {state}.')
    return redirect('authentification:admin_user_detail', pk=user.pk)


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


def _send_code_email(user, code):
    minutes = int(PasswordResetCode.LIFETIME.total_seconds() // 60)
    send_mail(
        'Votre code de réinitialisation CargoLink',
        (
            f'Bonjour {user.full_name},\n\n'
            f'Votre code de réinitialisation est : {code}\n\n'
            f'Il est valable {minutes} minutes. '
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\n"
            "L'équipe CargoLink"
        ),
        None,  # expéditeur : DEFAULT_FROM_EMAIL
        [user.email],
    )


# Étape 1 : saisie de l'adresse e-mail -> envoi du code
@require_http_methods(['GET', 'POST'])
def forget_password(request):
    form = ForgotPasswordForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        last_sent = request.session.get('reset_sent_at', 0)
        if request.session.get('reset_email') == email and time.time() - last_sent < RESEND_DELAY:
            wait = int(RESEND_DELAY - (time.time() - last_sent)) + 1
            form.add_error(None, f'Un code vient d’être envoyé. Patientez {wait} secondes avant d’en demander un autre.')
        else:
            # Même réponse que le compte existe ou non, pour ne pas révéler les adresses inscrites.
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            try:
                if user:
                    _send_code_email(user, PasswordResetCode.create_for(user))
            except (smtplib.SMTPException, OSError):
                PasswordResetCode.objects.filter(user=user).delete()
                form.add_error(None, 'L’envoi de l’e-mail a échoué. Réessayez dans quelques instants.')
            else:
                request.session['reset_email'] = email
                request.session['reset_sent_at'] = time.time()
                request.session.pop('reset_user_id', None)
                request.session.pop('reset_verified_at', None)
                return redirect('authentification:verify_code')
    initial_email = request.session.get('reset_email', '')
    return render(request, 'authentification/forget-password.html', {'form': form, 'initial_email': initial_email})


# Étape 2 : saisie du code reçu par e-mail
@require_http_methods(['GET', 'POST'])
def verify_code(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('authentification:forget_password')

    form = VerifyCodeForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        reset_code = PasswordResetCode.objects.select_related('user').filter(
            user__email__iexact=email, user__is_active=True,
        ).first()
        if reset_code is None or reset_code.is_expired or reset_code.attempts_left == 0:
            if reset_code:
                reset_code.delete()
            form.add_error(None, 'Ce code a expiré ou n’est plus valide. Demandez-en un nouveau.')
        elif reset_code.matches(form.cleaned_data['code']):
            request.session['reset_user_id'] = reset_code.user_id
            request.session['reset_verified_at'] = time.time()
            reset_code.delete()
            return redirect('authentification:reset_password')
        else:
            left = reset_code.attempts_left
            if left:
                form.add_error('code', f'Code incorrect. Il vous reste {left} tentative{"s" if left > 1 else ""}.')
            else:
                reset_code.delete()
                form.add_error(None, 'Trop de tentatives. Demandez un nouveau code.')
    return render(request, 'authentification/verify-code.html', {'form': form, 'email': email})


# Étape 3 : choix du nouveau mot de passe
@require_http_methods(['GET', 'POST'])
def reset_password(request):
    user_id = request.session.get('reset_user_id')
    verified_at = request.session.get('reset_verified_at', 0)
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if user is None or time.time() - verified_at > VERIFIED_LIFETIME:
        return redirect('authentification:forget_password')

    form = SetPasswordForm(user, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        PasswordResetCode.objects.filter(user=user).delete()
        for key in ('reset_email', 'reset_sent_at', 'reset_user_id', 'reset_verified_at'):
            request.session.pop(key, None)
        if user.role == User.Role.ADMIN:
            login(request, user)
            messages.success(request, 'Votre mot de passe a été modifié. Vous êtes connecté en tant qu’administrateur.')
            return redirect('authentification:admin_dashboard')
        messages.success(request, 'Votre mot de passe a été modifié. Vous pouvez vous connecter.')
        return redirect('authentification:login')
    return render(request, 'authentification/reset-password.html', {'form': form})

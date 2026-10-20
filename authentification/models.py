import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields['role'] = self.model.Role.ADMIN
        if not extra_fields['is_staff'] or not extra_fields['is_superuser']:
            raise ValueError('Un superutilisateur doit avoir les droits administrateur.')
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        PME = 'PME', 'PME'
        TRANSPORTEUR = 'transporteur', 'Transporteur'
        DESTINATAIRE = 'destinataire', 'Destinataire'

    username = None
    full_name = models.CharField('nom complet', max_length=150)
    email = models.EmailField('adresse e-mail', unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PME)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('email'), name='user_email_case_insensitive'),
        ]

    def __str__(self):
        return self.email


class PasswordResetCode(models.Model):
    """Code à 6 chiffres envoyé par e-mail pour réinitialiser le mot de passe."""

    LIFETIME = timedelta(minutes=10)
    MAX_ATTEMPTS = 5

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_codes')
    code = models.CharField(max_length=128)  # stocké haché, jamais en clair
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_for(cls, user):
        """Remplace les anciens codes de l'utilisateur et renvoie le nouveau code en clair."""
        cls.objects.filter(user=user).delete()
        plain_code = f'{secrets.randbelow(10 ** 6):06d}'
        cls.objects.create(user=user, code=make_password(plain_code))
        return plain_code

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + self.LIFETIME

    @property
    def attempts_left(self):
        return max(self.MAX_ATTEMPTS - self.attempts, 0)

    def matches(self, plain_code):
        """Compte une tentative puis compare le code saisi."""
        self.attempts += 1
        self.save(update_fields=['attempts'])
        return check_password(plain_code, self.code)

    def __str__(self):
        return f'Code de réinitialisation pour {self.user}'

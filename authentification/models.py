from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


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

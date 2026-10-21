from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from authentification.models import User


MAX_PHOTO_SIZE = 2 * 1024 * 1024
PHOTO_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']


def validate_photo_size(uploaded_file):
    if uploaded_file and uploaded_file.size > MAX_PHOTO_SIZE:
        raise ValidationError('La photo ne doit pas dépasser 2 Mo.')


class Vehicule(models.Model):
    class TypeVehicule(models.TextChoices):
        CAMIONNETTE = 'camionnette', 'Camionnette'
        CAMION = 'camion', 'Camion'
        SEMI_REMORQUE = 'semi_remorque', 'Semi-remorque'
        FRIGORIFIQUE = 'frigorifique', 'Frigorifique'
        PLATEAU = 'plateau', 'Plateau'
        AUTRE = 'autre', 'Autre'

    class Statut(models.TextChoices):
        ACTIF = 'actif', 'Actif'
        EN_MAINTENANCE = 'en_maintenance', 'En maintenance'
        DESACTIVE = 'desactive', 'Désactivé'

    transporteur = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='vehicules',
        limit_choices_to={'role': User.Role.TRANSPORTEUR},
        verbose_name='transporteur',
    )
    immatriculation = models.CharField('immatriculation', max_length=30, unique=True)
    marque = models.CharField('marque', max_length=80)
    modele = models.CharField('modèle', max_length=80)
    annee = models.PositiveSmallIntegerField('année')
    type_vehicule = models.CharField(
        'type de véhicule',
        max_length=20,
        choices=TypeVehicule.choices,
    )
    capacite_poids_kg = models.DecimalField(
        'capacité de poids (kg)',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    capacite_volume_m3 = models.DecimalField(
        'capacité de volume (m³)',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    statut = models.CharField(
        'statut',
        max_length=20,
        choices=Statut.choices,
        default=Statut.ACTIF,
    )
    photo = models.ImageField(
        'photo',
        upload_to='vehicules/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=PHOTO_EXTENSIONS),
            validate_photo_size,
        ],
    )
    date_creation = models.DateTimeField('date de création', auto_now_add=True)

    class Meta:
        ordering = ['-date_creation', '-pk']
        verbose_name = 'véhicule'
        verbose_name_plural = 'véhicules'
        indexes = [
            models.Index(fields=['transporteur', 'statut']),
            models.Index(fields=['type_vehicule', 'statut']),
            models.Index(fields=['immatriculation']),
        ]

    def clean(self):
        errors = {}
        if self.transporteur_id:
            transporteur = self.transporteur
            if transporteur.role != User.Role.TRANSPORTEUR:
                errors['transporteur'] = 'Le propriétaire doit avoir le rôle transporteur.'
        current_year = date.today().year
        if self.annee is not None and not 1980 <= self.annee <= current_year + 1:
            errors['annee'] = f"L'année doit être comprise entre 1980 et {current_year + 1}."
        if self.capacite_poids_kg is not None and self.capacite_poids_kg <= 0:
            errors['capacite_poids_kg'] = 'La capacité de poids doit être strictement positive.'
        if self.capacite_volume_m3 is not None and self.capacite_volume_m3 <= 0:
            errors['capacite_volume_m3'] = 'La capacité de volume doit être strictement positive.'
        if self.immatriculation:
            self.immatriculation = self.immatriculation.strip().upper()
            duplicate = Vehicule.objects.filter(immatriculation=self.immatriculation)
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors['immatriculation'] = 'Cette immatriculation est déjà utilisée.'
        if errors:
            raise ValidationError(errors)

    def delete(self, using=None, keep_parents=False):
        if self.disponibilites.filter(statut=Disponibilite.Statut.RESERVE).exists():
            raise ValidationError(
                'Ce véhicule possède une disponibilité réservée et ne peut pas être supprimé. '
                'Désactivez-le à la place.'
            )
        return super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return f'{self.immatriculation} — {self.marque} {self.modele}'


class Disponibilite(models.Model):
    class Statut(models.TextChoices):
        DISPONIBLE = 'disponible', 'Disponible'
        RESERVE = 'reserve', 'Réservé'
        INDISPONIBLE = 'indisponible', 'Indisponible'

    vehicule = models.ForeignKey(
        Vehicule,
        on_delete=models.CASCADE,
        related_name='disponibilites',
        verbose_name='véhicule',
    )
    date_debut = models.DateTimeField('date de début')
    date_fin = models.DateTimeField('date de fin')
    zone_depart = models.CharField('zone de départ', max_length=120)
    zone_arrivee = models.CharField('zone d’arrivée', max_length=120)
    statut = models.CharField(
        'statut',
        max_length=20,
        choices=Statut.choices,
        default=Statut.DISPONIBLE,
    )
    commentaire = models.TextField('commentaire', blank=True)

    class Meta:
        ordering = ['date_debut', 'pk']
        verbose_name = 'disponibilité'
        verbose_name_plural = 'disponibilités'
        indexes = [
            models.Index(fields=['vehicule', 'date_debut']),
            models.Index(fields=['vehicule', 'statut']),
            models.Index(fields=['date_debut', 'date_fin']),
        ]

    def clean(self):
        errors = {}
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            errors['date_fin'] = 'La date de fin doit être postérieure à la date de début.'
        if self._state.adding and self.date_debut and self.date_debut < timezone.now():
            errors['date_debut'] = 'La date de début ne peut pas être passée.'
        if self.vehicule_id:
            vehicule = self.vehicule
            if vehicule.statut in {Vehicule.Statut.EN_MAINTENANCE, Vehicule.Statut.DESACTIVE}:
                errors['vehicule'] = (
                    'Une disponibilité ne peut pas être créée pour un véhicule '
                    'en maintenance ou désactivé.'
                )
            if self.date_debut and self.date_fin and self.statut != self.Statut.INDISPONIBLE:
                overlapping = Disponibilite.objects.filter(
                    vehicule_id=self.vehicule_id,
                    statut__in=[self.Statut.DISPONIBLE, self.Statut.RESERVE],
                    date_debut__lt=self.date_fin,
                    date_fin__gt=self.date_debut,
                )
                if self.pk:
                    overlapping = overlapping.exclude(pk=self.pk)
                if overlapping.exists():
                    errors['date_debut'] = (
                        'Cette période chevauche une disponibilité active existante.'
                    )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.vehicule.immatriculation} — {self.zone_depart} → {self.zone_arrivee}'

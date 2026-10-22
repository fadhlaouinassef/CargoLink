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

                # Règle Sens 2 : refuse la création/modification d'une disponibilité chevauchant une maintenance
                from .models import Maintenance
                maint_overlap = Maintenance.objects.filter(
                    vehicule_id=self.vehicule_id,
                    statut__in=[Maintenance.Statut.PLANIFIEE, Maintenance.Statut.EN_COURS],
                    date_debut__lt=self.date_fin,
                    date_fin__gt=self.date_debut,
                )
                if maint_overlap.exists():
                    errors['date_debut'] = (
                        'Une maintenance est planifiée ou en cours pour ce véhicule sur cette période.'
                    )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.vehicule.immatriculation} — {self.zone_depart} → {self.zone_arrivee}'


class Maintenance(models.Model):
    class Motif(models.TextChoices):
        ENTRETIEN_PERIODIQUE = 'entretien_periodique', 'Entretien périodique'
        REPARATION = 'reparation', 'Réparation'
        CONTROLE_TECHNIQUE = 'controle_technique', 'Contrôle technique'
        PNEUS = 'pneus', 'Pneumatiques'
        AUTRE = 'autre', 'Autre'

    class Statut(models.TextChoices):
        PLANIFIEE = 'planifiee', 'Planifiée'
        EN_COURS = 'en_cours', 'En cours'
        TERMINEE = 'terminee', 'Terminée'
        ANNULEE = 'annulee', 'Annulée'

    vehicule = models.ForeignKey(
        Vehicule,
        on_delete=models.CASCADE,
        related_name='maintenances',
        verbose_name='véhicule',
    )
    date_debut = models.DateTimeField('date de début')
    date_fin = models.DateTimeField('date de fin')
    motif = models.CharField(
        'motif',
        max_length=30,
        choices=Motif.choices,
        default=Motif.ENTRETIEN_PERIODIQUE,
    )
    statut = models.CharField(
        'statut',
        max_length=20,
        choices=Statut.choices,
        default=Statut.PLANIFIEE,
    )
    commentaire = models.TextField('commentaire', blank=True)
    date_creation = models.DateTimeField('date de création', auto_now_add=True)

    class Meta:
        ordering = ['-date_debut', '-pk']
        verbose_name = 'maintenance'
        verbose_name_plural = 'maintenances'
        indexes = [
            models.Index(fields=['vehicule', 'date_debut', 'date_fin']),
            models.Index(fields=['vehicule', 'statut']),
            models.Index(fields=['date_debut', 'date_fin']),
        ]

    def clean(self):
        errors = {}

        # 7. Une maintenance "terminee" n'est ni modifiable ni supprimable (historique).
        if self.pk:
            old = Maintenance.objects.filter(pk=self.pk).first()
            if old and old.statut == self.Statut.TERMINEE and self.statut == self.Statut.TERMINEE:
                # Vérifier si des champs de dates/motif/véhicule ont été altérés
                if (old.date_debut != self.date_debut or old.date_fin != self.date_fin
                        or old.motif != self.motif or old.vehicule_id != self.vehicule_id):
                    raise ValidationError("Une maintenance terminée ne peut plus être modifiée (archivage historique).")

        # 1. date_fin > date_debut
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            errors['date_fin'] = 'La date de fin doit être postérieure à la date de début.'

        # 2. Une nouvelle maintenance ne commence pas dans le passé (à la création uniquement)
        if self._state.adding and self.date_debut and self.date_debut < timezone.now():
            errors['date_debut'] = 'La date de début ne peut pas être passée.'

        if self.vehicule_id and self.date_debut and self.date_fin:
            # 3. Pas de chevauchement avec une autre maintenance du même véhicule (planifiee ou en_cours)
            # Règle de chevauchement strict : debut_A < fin_B ET fin_A > debut_B (fin == début autorisé)
            if self.statut in {self.Statut.PLANIFIEE, self.Statut.EN_COURS}:
                chevauchement_maint = Maintenance.objects.filter(
                    vehicule_id=self.vehicule_id,
                    statut__in=[self.Statut.PLANIFIEE, self.Statut.EN_COURS],
                    date_debut__lt=self.date_fin,
                    date_fin__gt=self.date_debut,
                )
                if self.pk:
                    chevauchement_maint = chevauchement_maint.exclude(pk=self.pk)
                if chevauchement_maint.exists():
                    errors['date_debut'] = (
                        'Cette période chevauche une autre maintenance planifiée ou en cours pour ce véhicule.'
                    )

            # 5. Pas de chevauchement avec une Disponibilite de statut "reserve"
            dispo_reserve = Disponibilite.objects.filter(
                vehicule_id=self.vehicule_id,
                statut=Disponibilite.Statut.RESERVE,
                date_debut__lt=self.date_fin,
                date_fin__gt=self.date_debut,
            )
            if dispo_reserve.exists():
                errors['date_debut'] = (
                    'Ce véhicule possède une disponibilité réservée (transport confirmé) sur cette période.'
                )

            # 4. Règle clé : Pas de chevauchement avec un trajet confirmé (ou en cours) du même véhicule
            if self.statut in {self.Statut.PLANIFIEE, self.Statut.EN_COURS}:
                from .services import trajets_actifs_en_conflit, formater_conflit_trajet
                conflits = trajets_actifs_en_conflit(self.vehicule, self.date_debut, self.date_fin)
                if conflits:
                    descriptions = [formater_conflit_trajet(c) for c in conflits]
                    if len(descriptions) == 1:
                        msg = (
                            f"Impossible de programmer cette maintenance : le véhicule est affecté au "
                            f"{descriptions[0]}. Réaffectez le trajet à un autre véhicule ou choisissez "
                            f"une autre période de maintenance."
                        )
                    else:
                        liste_str = " ; ".join(descriptions)
                        msg = (
                            f"Impossible de programmer cette maintenance : le véhicule est affecté aux trajets suivants : "
                            f"{liste_str}. Réaffectez ces trajets à un autre véhicule ou choisissez une autre période de maintenance."
                        )
                    errors['date_debut'] = msg

        if errors:
            raise ValidationError(errors)

    def delete(self, using=None, keep_parents=False):
        if self.statut == self.Statut.TERMINEE:
            raise ValidationError("Une maintenance terminée ne peut pas être supprimée (archivage historique).")
        return super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return f'{self.vehicule.immatriculation} — {self.get_motif_display()} ({self.date_debut:%d/%m/%Y})'

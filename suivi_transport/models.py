from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from vehicules.models import validate_photo_size


class Transport(models.Model):
    class Statut(models.TextChoices):
        PLANIFIE = 'planifie', 'Planifié'
        PRIS_EN_CHARGE = 'pris_en_charge', 'Pris en charge'
        EN_TRANSIT = 'en_transit', 'En transit'
        ARRIVE = 'arrive', 'Arrivé à destination'
        LIVRE = 'livre', 'Livré'
        ANNULE = 'annule', 'Annulé'

    offre = models.OneToOneField(
        'gestion_trajets.OffreTransport', on_delete=models.PROTECT, related_name='transport_suivi',
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PLANIFIE)
    date_prise_en_charge = models.DateTimeField(null=True, blank=True)
    date_arrivee = models.DateTimeField(null=True, blank=True)
    date_confirmation_reception = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def demande(self):
        return self.offre.demande

    @property
    def trajet(self):
        return self.offre.trajet

    @property
    def transporteur(self):
        return self.offre.transporteur

    @property
    def badge_class(self):
        mapping = {
            self.Statut.PLANIFIE: 'badge-draft',
            self.Statut.PRIS_EN_CHARGE: 'badge-pending',
            self.Statut.EN_TRANSIT: 'badge-active',
            self.Statut.ARRIVE: 'badge-offers',
            self.Statut.LIVRE: 'badge-success',
            self.Statut.ANNULE: 'badge-danger',
        }
        return mapping.get(self.statut, 'badge-active')

    def get_statut_display(self):
        if self.statut == 'incident':
            return 'Ancien statut incident'
        return dict(self.Statut.choices).get(self.statut, self.statut)

    def __str__(self):
        return f'TR-{self.pk:04d}'


class EvenementSuivi(models.Model):
    transport = models.ForeignKey(Transport, on_delete=models.CASCADE, related_name='evenements')
    statut = models.CharField(max_length=20, choices=Transport.Statut.choices)
    titre = models.CharField(max_length=150)
    description = models.TextField(blank=True, max_length=2000)
    lieu = models.CharField(max_length=150, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    date_evenement = models.DateTimeField(default=timezone.now)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='evenements_suivi_crees',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_evenement', '-pk']

    @property
    def badge_class(self):
        mapping = {
            Transport.Statut.PLANIFIE: 'badge-draft',
            Transport.Statut.PRIS_EN_CHARGE: 'badge-pending',
            Transport.Statut.EN_TRANSIT: 'badge-active',
            Transport.Statut.ARRIVE: 'badge-offers',
            Transport.Statut.LIVRE: 'badge-success',
            Transport.Statut.ANNULE: 'badge-danger',
        }
        return mapping.get(self.statut, 'badge-active')

    def get_statut_display(self):
        if self.statut == 'incident':
            return 'Ancien événement incident'
        return dict(Transport.Statut.choices).get(self.statut, self.statut)

    def __str__(self):
        return f'{self.titre} · {self.transport}'


class IncidentTransport(models.Model):
    class Categorie(models.TextChoices):
        PANNE = 'panne', 'Panne du véhicule'
        ACCIDENT = 'accident', 'Accident'
        MARCHANDISE = 'marchandise', 'Marchandise endommagée ou manquante'
        RETARD = 'retard', 'Retard important'
        SECURITE = 'securite', 'Sécurité'
        AUTRE = 'autre', 'Autre'

    class Priorite(models.TextChoices):
        BASSE = 'basse', 'Basse'
        NORMALE = 'normale', 'Normale'
        HAUTE = 'haute', 'Haute'
        URGENTE = 'urgente', 'Urgente'

    class Etat(models.TextChoices):
        SIGNALE = 'signale', 'Signalé'
        EN_COURS = 'en_cours', 'En cours de traitement'
        RESOLU = 'resolu', 'Résolu'

    transport = models.ForeignKey(Transport, on_delete=models.CASCADE, related_name='incidents')
    signale_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='incidents_transport_signales',
    )
    categorie = models.CharField(max_length=20, choices=Categorie.choices)
    description = models.TextField(max_length=3000)
    priorite = models.CharField(max_length=10, choices=Priorite.choices, default=Priorite.NORMALE)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    photo = models.ImageField(
        upload_to='incidents-transport/', blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp']), validate_photo_size],
    )
    etat = models.CharField(max_length=12, choices=Etat.choices, default=Etat.SIGNALE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(fields=['etat', 'priorite', 'created_at'], name='incident_etat_prio_date_idx'),
            models.Index(fields=['transport', 'etat'], name='incident_transport_etat_idx'),
        ]

    @property
    def badge_class(self):
        return {
            self.Etat.SIGNALE: 'badge-danger',
            self.Etat.EN_COURS: 'badge-pending',
            self.Etat.RESOLU: 'badge-success',
        }.get(self.etat, 'badge-draft')

    @property
    def priority_class(self):
        return {
            self.Priorite.BASSE: 'incident-priority-low',
            self.Priorite.NORMALE: 'incident-priority-normal',
            self.Priorite.HAUTE: 'incident-priority-high',
            self.Priorite.URGENTE: 'incident-priority-urgent',
        }.get(self.priorite, 'incident-priority-normal')

    def __str__(self):
        return f'Incident #{self.pk} · {self.transport}'


class HistoriqueIncident(models.Model):
    incident = models.ForeignKey(IncidentTransport, on_delete=models.CASCADE, related_name='historique')
    etat = models.CharField(max_length=12, choices=IncidentTransport.Etat.choices)
    commentaire = models.CharField(max_length=1500, blank=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='historique_incidents_transport',
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['created_at', 'pk']
        verbose_name = 'historique d’incident'
        verbose_name_plural = 'historiques d’incidents'

    def __str__(self):
        return f'{self.incident} · {self.get_etat_display()}'

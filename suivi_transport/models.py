from django.conf import settings
from django.db import models
from django.utils import timezone


class Transport(models.Model):
    class Statut(models.TextChoices):
        PLANIFIE = 'planifie', 'Planifié'
        PRIS_EN_CHARGE = 'pris_en_charge', 'Pris en charge'
        EN_TRANSIT = 'en_transit', 'En transit'
        ARRIVE = 'arrive', 'Arrivé à destination'
        LIVRE = 'livre', 'Livré'
        INCIDENT = 'incident', 'Incident signalé'
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
            self.Statut.INCIDENT: 'badge-danger',
            self.Statut.ANNULE: 'badge-danger',
        }
        return mapping.get(self.statut, 'badge-active')

    def __str__(self):
        return f'TR-{self.pk:04d}'


class EvenementSuivi(models.Model):
    transport = models.ForeignKey(Transport, on_delete=models.CASCADE, related_name='evenements')
    statut = models.CharField(max_length=20, choices=Transport.Statut.choices)
    titre = models.CharField(max_length=150)
    description = models.TextField(blank=True, max_length=2000)
    lieu = models.CharField(max_length=150, blank=True)
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
            Transport.Statut.INCIDENT: 'badge-danger',
            Transport.Statut.ANNULE: 'badge-danger',
        }
        return mapping.get(self.statut, 'badge-active')

    def __str__(self):
        return f'{self.titre} · {self.transport}'

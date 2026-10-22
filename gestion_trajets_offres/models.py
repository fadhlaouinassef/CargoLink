from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Trajet(models.Model):
    class Statut(models.TextChoices):
        PUBLIE = 'publie', 'Publié'
        EN_COURS = 'en_cours', 'En cours'
        TERMINE = 'termine', 'Terminé'
        ANNULE = 'annule', 'Annulé'

    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trajets')
    depart_ville = models.CharField('Ville de départ', max_length=100)
    arrivee_ville = models.CharField("Ville d’arrivée", max_length=100)
    date_depart = models.DateTimeField('Date et heure de départ')
    vehicule = models.CharField('Véhicule / immatriculation', max_length=100)
    capacite_kg = models.DecimalField('Capacité disponible (kg)', max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    volume_m3 = models.DecimalField('Volume disponible (m³)', max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    statut = models.CharField('État du trajet', max_length=12, choices=Statut.choices, default=Statut.PUBLIE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_depart']
        constraints = [
            models.CheckConstraint(condition=models.Q(capacite_kg__gt=0), name='trajet_capacite_positive'),
            models.CheckConstraint(condition=models.Q(volume_m3__gt=0), name='trajet_volume_positif'),
        ]

    def __str__(self):
        return f'{self.depart_ville} → {self.arrivee_ville} ({self.date_depart:%d/%m/%Y})'


class OffreTransport(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente'
        ACCEPTEE = 'acceptee', 'Acceptée'
        REFUSEE = 'refusee', 'Non retenue'

    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='offres_transport')
    demande = models.ForeignKey('demandes.DemandeTransport', on_delete=models.CASCADE, related_name='offres_transport')
    trajet = models.ForeignKey(Trajet, on_delete=models.PROTECT, related_name='offres')
    prix = models.DecimalField('Prix proposé (TND)', max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    message = models.TextField('Message à la PME', blank=True, max_length=2000)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['transporteur', 'demande'], name='offre_unique_transporteur_demande'),
            models.CheckConstraint(condition=models.Q(prix__gt=0), name='offre_prix_positif'),
        ]

    def __str__(self):
        return f'OFF-{self.pk} → {self.prix} TND'

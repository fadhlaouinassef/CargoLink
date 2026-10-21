from django.conf import settings
from django.db import models


class DemandeTransport(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = 'brouillon', 'Brouillon'
        OUVERTE = 'ouverte', 'En recherche de transporteur'

    class ModalitePaiement(models.TextChoices):
        LIVRAISON = 'livraison', 'À la livraison'
        ENLEVEMENT = 'enlevement', "À l'enlèvement"
        TERME = 'terme', 'Virement à 30 jours'

    class ValiditeOffres(models.TextChoices):
        VINGT_QUATRE_HEURES = '24h', '24 heures'
        QUARANTE_HUIT_HEURES = '48h', '48 heures'
        SOIXANTE_DOUZE_HEURES = '72h', '3 jours'

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_transport',
    )
    owner_session = models.CharField(max_length=40, blank=True, null=True)
    statut = models.CharField(
        max_length=12,
        choices=Statut.choices,
        default=Statut.OUVERTE,
    )
    depart_ville = models.CharField(max_length=100)
    depart_adresse = models.CharField(max_length=255)
    date_depart = models.DateField()
    arrivee_ville = models.CharField(max_length=100)
    arrivee_adresse = models.CharField(max_length=255)
    date_limite = models.DateField()
    destinataire_nom = models.CharField(max_length=150)
    destinataire_contact = models.CharField(max_length=150)
    destinataire_tel = models.CharField(max_length=30)
    hayon = models.BooleanField(default=False)
    transpalette = models.BooleanField(default=False)
    bache = models.BooleanField(default=False)
    consignes = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    modalite_paiement = models.CharField(
        max_length=20,
        choices=ModalitePaiement.choices,
        default=ModalitePaiement.LIVRAISON,
    )
    validite_offres = models.CharField(
        max_length=3,
        choices=ValiditeOffres.choices,
        default=ValiditeOffres.QUARANTE_HUIT_HEURES,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'demande de transport'
        verbose_name_plural = 'demandes de transport'

    def __str__(self):
        return f'DEM-{self.created_at:%Y}-{self.pk:04d}' if self.pk else 'Nouvelle demande'


class Marchandise(models.Model):
    class Type(models.TextChoices):
        PALETTES = 'palettes', 'Palettes Euro standard (80x120)'
        CARTONS = 'cartons', 'Cartons / Colis groupés'
        VRAC = 'vrac', 'Vrac sécurisé'
        FRAIS = 'frais', 'Température dirigée (frais)'
        MACHINES = 'machines', 'Équipement / Machines'

    demande = models.ForeignKey(
        DemandeTransport,
        on_delete=models.CASCADE,
        related_name='marchandises',
    )
    description = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.PALETTES)
    poids = models.DecimalField(max_digits=10, decimal_places=2)
    volume = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fragile = models.BooleanField(default=False)

    class Meta:
        ordering = ('pk',)
        verbose_name = 'marchandise'
        verbose_name_plural = 'marchandises'

    def __str__(self):
        return self.description

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count

# Limites de saisie, partagées par les modèles et les formulaires.
AVIS_COMMENTAIRE_MIN = 10
AVIS_COMMENTAIRE_MAX = 1000
RECLAMATION_DESCRIPTION_MIN = 15
RECLAMATION_DESCRIPTION_MAX = 2000
REPONSE_MIN = 10
REPONSE_MAX = 2000
MOTIF_MODERATION_MIN = 5
MOTIF_MODERATION_MAX = 200


class AvisQuerySet(models.QuerySet):
    def publies(self):
        return self.filter(statut=Avis.Statut.PUBLIE)

    def stats(self):
        """Note moyenne et nombre d'avis (à appeler sur des avis publiés)."""
        result = self.aggregate(moyenne=Avg('note'), total=Count('pk'))
        moyenne = result['moyenne']
        return {
            'moyenne': moyenne,
            'arrondie': int(moyenne + 0.5) if moyenne else 0,  # pour afficher les étoiles
            'total': result['total'],
        }


class Avis(models.Model):
    """Évaluation d'un transporteur par une PME, à propos d'une demande de transport."""

    class Statut(models.TextChoices):
        PUBLIE = 'publie', 'Publié'
        MASQUE = 'masque', 'Masqué par la modération'

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='avis_donnes',
    )
    transporteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='avis_recus',
    )
    demande = models.ForeignKey('demandes.DemandeTransport', on_delete=models.CASCADE, related_name='avis')
    note = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire = models.TextField(max_length=AVIS_COMMENTAIRE_MAX)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PUBLIE)
    motif_moderation = models.CharField(max_length=MOTIF_MODERATION_MAX, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AvisQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'avis'
        verbose_name_plural = 'avis'
        constraints = [
            models.UniqueConstraint(fields=('auteur', 'demande'), name='avis_unique_par_auteur_et_demande'),
            models.CheckConstraint(condition=models.Q(note__gte=1, note__lte=5), name='avis_note_entre_1_et_5'),
        ]

    @property
    def est_publie(self):
        return self.statut == self.Statut.PUBLIE

    def __str__(self):
        return f'{self.note}/5 · {self.auteur} → {self.transporteur}'


class Reclamation(models.Model):
    """Litige déposé par une PME ou un destinataire, instruit par l'administrateur."""

    class Motif(models.TextChoices):
        AVARIE = 'avarie', 'Marchandise endommagée'
        MANQUANT = 'manquant', 'Colis ou marchandise manquante'
        RETARD = 'retard', 'Retard important'
        NON_CONFORME = 'non_conforme', 'Marchandise ou véhicule non conforme'
        COMPORTEMENT = 'comportement', 'Comportement inapproprié'
        AUTRE = 'autre', 'Autre motif'

    class Statut(models.TextChoices):
        OUVERTE = 'ouverte', 'Ouverte'
        EN_COURS = 'en_cours', 'En instruction'
        RESOLUE = 'resolue', 'Résolue'
        REJETEE = 'rejetee', 'Rejetée'

    # Statuts autorisés depuis chaque statut : une réclamation clôturée ne se rouvre pas.
    TRANSITIONS = {
        Statut.OUVERTE: (Statut.EN_COURS, Statut.RESOLUE, Statut.REJETEE),
        Statut.EN_COURS: (Statut.RESOLUE, Statut.REJETEE),
        Statut.RESOLUE: (),
        Statut.REJETEE: (),
    }

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reclamations_deposees',
    )
    demande = models.ForeignKey('demandes.DemandeTransport', on_delete=models.CASCADE, related_name='reclamations')
    transporteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reclamations_recues',
    )
    motif = models.CharField(max_length=20, choices=Motif.choices)
    description = models.TextField(max_length=RECLAMATION_DESCRIPTION_MAX)
    montant_prejudice = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
    )
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERTE)
    reponse_admin = models.TextField(blank=True, max_length=REPONSE_MAX)
    traitee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reclamations_traitees',
    )
    traitee_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'réclamation'
        verbose_name_plural = 'réclamations'

    @property
    def reference(self):
        return f'REC-{self.created_at:%Y}-{self.pk:04d}' if self.pk else 'Nouvelle réclamation'

    @property
    def est_close(self):
        return not self.TRANSITIONS[self.statut]

    @property
    def est_modifiable(self):
        """L'auteur peut modifier ou supprimer sa réclamation tant que l'administrateur ne l'a pas prise en charge."""
        return self.statut == self.Statut.OUVERTE

    def statuts_suivants(self):
        """Statuts que l'administrateur peut choisir à partir du statut actuel."""
        return [(value, self.Statut(value).label) for value in self.TRANSITIONS[self.statut]]

    def __str__(self):
        return f'{self.reference} · {self.get_motif_display()}'

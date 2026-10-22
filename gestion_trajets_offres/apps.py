from django.apps import AppConfig


class GestionTrajetsOffresConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'gestion_trajets_offres'
    # Keep the existing migration history and database table names.
    label = 'gestion_trajets'
    verbose_name = 'Gestion des trajets et des offres'

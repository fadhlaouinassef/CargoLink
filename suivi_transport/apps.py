from django.apps import AppConfig


class SuiviTransportConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'suivi_transport'
    verbose_name = 'Suivi des transports'

    def ready(self):
        from . import signals  # noqa: F401

# Import optionnel de Celery : le projet continue de démarrer chez les coéquipiers
# qui n'ont pas encore installé celery (uv add celery redis).
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass

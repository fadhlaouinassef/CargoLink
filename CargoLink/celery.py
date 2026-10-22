"""Configuration Celery pour le projet CargoLink.

Le .env est chargé par settings.py avant que ce module soit importé,
donc le worker hérite des variables CELERY_BROKER_URL et GEMINI_API_KEY
dès lors qu'il est lancé avec la commande :
  uv run celery -A CargoLink worker -P solo -l info
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CargoLink.settings')

app = Celery('CargoLink')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Planification nocturne : analyse de la flotte complète à 02:00 (Africa/Tunis)
app.conf.beat_schedule = {
    'analyser-flotte-nocturne': {
        'task': 'vehicules.tasks.analyser_flotte_task',
        'schedule': crontab(hour=2, minute=0),
    },
}

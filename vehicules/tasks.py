"""Tâches Celery pour l'analyse du risque de maintenance.

Commandes pour lancer le worker (Windows, pool solo car prefork non supporté) :
  uv run celery -A CargoLink worker -P solo -l info
  uv run celery -A CargoLink beat -l info
  uv run celery -A CargoLink flower  (optionnel, pour monitoring)

Redis requis (exemple Docker/WSL) :
  docker run --rm -p 6379:6379 redis:alpine
  # OU via WSL : sudo service redis-server start
  # OU Memurai (Windows natif) : https://www.memurai.com/
"""
import logging
import time

try:
    from celery import shared_task
except ImportError:
    # Si celery n'est pas installé, décorateur factice pour que l'app charge sans erreur
    class _MockTaskResult:
        def __init__(self, result):
            self._result = result
        def get(self):
            return self._result

    def shared_task(*args, **kwargs):
        bind = kwargs.get('bind', False)
        def decorator(func):
            def delay(*fargs, **fkwargs):
                class _MockSelf:
                    request = type('_Req', (), {'id': 'mock-task-id', 'retries': 0})()
                    def retry(self, *a, **kw): pass
                mock_self = _MockSelf()
                res = func(mock_self, *fargs, **fkwargs) if bind else func(*fargs, **fkwargs)
                return _MockTaskResult(res)
            func.delay = delay
            return func
        if len(args) == 1 and callable(args[0]):
            return decorator(args[0])
        return decorator

from django.conf import settings

logger = logging.getLogger(__name__)

_RETRIES_MAX = 3
_RETRY_BACKOFF_SECONDS = (10, 30, 90)


@shared_task(bind=True, max_retries=_RETRIES_MAX, name='vehicules.tasks.analyser_vehicule_task')
def analyser_vehicule_task(self, vehicule_id: int, force: bool = False):
    """Analyse le risque de maintenance d'un véhicule en arrière-plan.

    - Idempotente : si le véhicule a été supprimé, la tâche se termine proprement.
    - Nouvelles tentatives avec backoff croissant sur quota IA ou timeout.
    - Ne plante jamais la queue sur une exception inattendue.

    Args:
        vehicule_id: PK du véhicule à analyser.
        force: Si True, ignore le cache hash et rappelle l'API.
    """
    from vehicules.services import analyser_vehicule
    from vehicules.ia.providers import IAQuotaExceededError, IATimeoutError

    try:
        analyse = analyser_vehicule(vehicule_id, force=force)
        if analyse is None:
            logger.warning("analyser_vehicule_task : véhicule %d introuvable ou supprimé.", vehicule_id)
            return {'statut': 'vehicule_introuvable', 'vehicule_id': vehicule_id}
        return {
            'statut': 'ok',
            'vehicule_id': vehicule_id,
            'analyse_id': analyse.pk,
            'niveau': analyse.niveau,
            'source': analyse.source,
        }
    except (IAQuotaExceededError, IATimeoutError) as exc:
        tentative = self.request.retries
        if tentative < _RETRIES_MAX:
            attente = _RETRY_BACKOFF_SECONDS[tentative] if tentative < len(_RETRY_BACKOFF_SECONDS) else 90
            logger.warning(
                "analyser_vehicule_task %d : quota/timeout (tentative %d/%d), retry dans %ds.",
                vehicule_id, tentative + 1, _RETRIES_MAX, attente,
            )
            raise self.retry(exc=exc, countdown=attente)
        logger.error("analyser_vehicule_task %d : max retries atteint.", vehicule_id)
        return {'statut': 'erreur_quota', 'vehicule_id': vehicule_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("analyser_vehicule_task %d : erreur inattendue : %s", vehicule_id, exc)
        return {'statut': 'erreur', 'vehicule_id': vehicule_id, 'detail': str(exc)}


@shared_task(name='vehicules.tasks.analyser_flotte_task')
def analyser_flotte_task():
    """Analyse tous les véhicules actifs de la flotte, avec cadence limitée.

    - Saute les véhicules dont le hash des données n'a pas changé (économie de quota).
    - Pause IA_RISQUE_PAUSE_SECONDS entre chaque appel pour le quota gratuit.
    - Journalise un résumé détaillé à la fin.
    """
    from vehicules.models import Vehicule
    from vehicules.services import analyser_vehicule
    from vehicules.ia.providers import IAQuotaExceededError, IATimeoutError
    from vehicules.ia.risque_regles import calculer_variables, score_regles
    from vehicules.ia.risque_assistant import calculer_hash_variables
    from vehicules.models import AnalyseRisque
    from django.utils import timezone
    from datetime import timedelta

    pause = getattr(settings, 'IA_RISQUE_PAUSE_SECONDS', 6.0)
    vehicules_actifs = list(Vehicule.objects.filter(statut=Vehicule.Statut.ACTIF))
    t_global = time.monotonic()

    stats = {'analyses': 0, 'ignores_hash': 0, 'replis': 0, 'erreurs': 0}

    for vehicule in vehicules_actifs:
        try:
            # Pré-vérification du hash avant appel API (économie)
            variables = calculer_variables(vehicule)
            donnees_hash = calculer_hash_variables(variables)
            seuil = timezone.now() - timedelta(hours=24)
            existante = AnalyseRisque.objects.filter(
                vehicule=vehicule, donnees_hash=donnees_hash, date_analyse__gte=seuil
            ).exists()
            if existante:
                stats['ignores_hash'] += 1
                continue

            analyse = analyser_vehicule(vehicule.pk, force=False)
            if analyse is None:
                stats['erreurs'] += 1
                continue
            if analyse.source == 'regles':
                stats['replis'] += 1
            else:
                stats['analyses'] += 1

            time.sleep(pause)

        except Exception as exc:  # noqa: BLE001
            logger.error("analyser_flotte_task : erreur sur véhicule %d : %s", vehicule.pk, exc)
            stats['erreurs'] += 1

    duree_totale = int(time.monotonic() - t_global)
    logger.info(
        "analyser_flotte_task terminé : %d analysés, %d ignorés (hash), %d replis, %d erreurs — durée %ds",
        stats['analyses'], stats['ignores_hash'], stats['replis'], stats['erreurs'], duree_totale,
    )
    return {**stats, 'duree_totale_s': duree_totale, 'total_vehicules': len(vehicules_actifs)}

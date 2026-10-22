"""Vues dédiées à l'assistance IA pour le module véhicules."""
import json
import logging
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.views import View

from vehicules.ia.assistant import AssistantDisponibilite
from vehicules.ia.providers import (
    IAConfigurationError,
    IAProviderError,
    IAQuotaExceededError,
    IATimeoutError,
    IAUnavailableError,
)
from vehicules.views import TransporteurRequiredMixin

logger = logging.getLogger(__name__)

# Limitation de fréquence : maximum 10 requêtes par minute par utilisateur
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60


class AssistantDisponibiliteIAView(TransporteurRequiredMixin, View):
    """Endpoint HTTP pour l'extraction IA des données de disponibilité.

    - POST uniquement
    - CSRF obligatoire (géré par Django standard)
    - Réservé aux utilisateurs connectés ayant le rôle transporteur
    - Limitation de fréquence via le cache Django (10 req/min)
    - N'écrit JAMAIS en base de données
    - Journalisation du temps de réponse et erreurs, SANS la clé API
    """

    assistant_class = AssistantDisponibilite

    def post(self, request, *args, **kwargs):
        user_id = request.user.pk
        cache_key = f"ia_rate_limit_vehicules_{user_id}"

        # Limitation de fréquence via cache Django
        count = cache.get(cache_key, 0)
        if count >= RATE_LIMIT_REQUESTS:
            logger.warning(
                "Quota de requêtes IA par minute dépassé pour transporteur_id=%s (count=%s)",
                user_id,
                count,
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Trop de requêtes. Veuillez patienter une minute avant de réutiliser l'assistant IA.",
                    "code": "rate_limit_exceeded",
                },
                status=429,
            )

        # Décodage du body JSON
        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Requête invalide : format JSON attendu.",
                    "code": "invalid_request_body",
                },
                status=400,
            )

        phrase = (payload.get("phrase") or "").strip()
        if len(phrase) < 3:
            return JsonResponse(
                {
                    "success": False,
                    "error": "La phrase est trop courte (minimum 3 caractères).",
                    "code": "phrase_too_short",
                },
                status=400,
            )
        if len(phrase) > 300:
            return JsonResponse(
                {
                    "success": False,
                    "error": "La phrase est trop longue (maximum 300 caractères).",
                    "code": "phrase_too_long",
                },
                status=400,
            )

        # Incrément du compteur de requêtes
        try:
            if count == 0:
                cache.set(cache_key, 1, timeout=RATE_LIMIT_WINDOW_SECONDS)
            else:
                cache.incr(cache_key)
        except Exception as e:
            logger.warning("Échec de mise à jour du cache de rate limit: %s", e)

        start_time = time.time()
        assistant = self.assistant_class()

        try:
            result = assistant.process_phrase(phrase=phrase, user=request.user)
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Assistant IA succès : transporteur_id=%s, durée=%sms, chars=%s",
                user_id,
                duration_ms,
                len(phrase),
            )
            return JsonResponse(result, status=200)

        except IATimeoutError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Assistant IA timeout : transporteur_id=%s, durée=%sms, erreur=%s",
                user_id,
                duration_ms,
                e.message,
            )
            return JsonResponse(
                {"success": False, "error": e.message, "code": e.code},
                status=504,
            )

        except IAQuotaExceededError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Assistant IA quota fournisseur dépassé : transporteur_id=%s, durée=%sms",
                user_id,
                duration_ms,
            )
            return JsonResponse(
                {"success": False, "error": e.message, "code": e.code},
                status=429,
            )

        except (IAConfigurationError, IAUnavailableError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Assistant IA service indisponible : transporteur_id=%s, durée=%sms, erreur=%s",
                user_id,
                duration_ms,
                e.message,
            )
            return JsonResponse(
                {"success": False, "error": e.message, "code": e.code},
                status=503,
            )

        except IAProviderError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Assistant IA erreur provider : transporteur_id=%s, durée=%sms, code=%s",
                user_id,
                duration_ms,
                e.code,
            )
            return JsonResponse(
                {"success": False, "error": e.message, "code": e.code},
                status=e.status_code if 400 <= e.status_code < 600 else 502,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Assistant IA erreur inattendue : transporteur_id=%s, durée=%sms, err=%s",
                user_id,
                duration_ms,
                type(e).__name__,
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Une erreur inattendue s'est produite lors de l'analyse.",
                    "code": "internal_error",
                },
                status=500,
            )

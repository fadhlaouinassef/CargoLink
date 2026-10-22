"""Fournisseur IA (Google Gemini REST / interchangeable).

Ce module isole totalement l'appel au fournisseur LLM sans dépendance externe
(utilise uniquement le module standard `urllib`).
Aucune clé ni URL n'est codée en dur. Tout provient des variables d'environnement.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict

logger = logging.getLogger(__name__)


class IAProviderError(Exception):
    """Erreur de base pour les appels aux fournisseurs IA."""
    def __init__(self, message: str, code: str = 'provider_error', status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class IATimeoutError(IAProviderError):
    def __init__(self, message: str = "Le service IA a mis trop de temps à répondre."):
        super().__init__(message, code='timeout', status_code=504)


class IAQuotaExceededError(IAProviderError):
    def __init__(self, message: str = "Le quota du service IA a été dépassé. Réessayez dans un instant."):
        super().__init__(message, code='quota_exceeded', status_code=429)


class IAConfigurationError(IAProviderError):
    def __init__(self, message: str = "Le service IA n'est pas configuré correctement."):
        super().__init__(message, code='config_error', status_code=503)


class IAUnavailableError(IAProviderError):
    def __init__(self, message: str = "Le service IA est temporairement indisponible."):
        super().__init__(message, code='unavailable', status_code=503)


class GeminiProvider:
    """Fournisseur d'IA basé sur l'API REST Google Gemini."""

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float | None = None):
        self.api_key = (api_key or os.environ.get('GEMINI_API_KEY', '')).strip()
        self.model = (model or os.environ.get('GEMINI_MODEL', '')).strip() or 'gemini-3.5-flash-lite'
        raw_timeout = timeout or os.environ.get('IA_TIMEOUT_SECONDS', '15')
        try:
            self.timeout = float(raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 15.0

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """Appelle l'API Gemini et renvoie le texte brut de la réponse (JSON attendu)."""
        if not self.api_key:
            logger.error("Appel IA rejeté : clé GEMINI_API_KEY absente.")
            raise IAConfigurationError("Clé API IA non configurée.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }

        data = json.dumps(payload).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode('utf-8')
                result = json.loads(body)
                candidates = result.get('candidates', [])
                if not candidates:
                    raise IAProviderError("Aucune réponse générée par l'IA.", code='empty_response')
                content_parts = candidates[0].get('content', {}).get('parts', [])
                if not content_parts or 'text' not in content_parts[0]:
                    raise IAProviderError("Format de réponse inattendu de l'IA.", code='malformed_response')
                return content_parts[0]['text']

        except urllib.error.HTTPError as e:
            status = e.code
            try:
                error_body = e.read().decode('utf-8')
            except Exception:
                error_body = ''
            logger.warning("Erreur HTTP de l'API Gemini : status=%s, type=%s", status, e.reason)

            if status == 429:
                raise IAQuotaExceededError()
            if status in (401, 403):
                raise IAConfigurationError("Clé API IA invalide ou non autorisée.")
            if status == 404:
                raise IAConfigurationError(f"Modèle IA introuvable : {self.model}.")
            if status in (500, 502, 503, 504):
                raise IAUnavailableError("Le service Gemini rencontre une surcharge momentanée.")
            raise IAProviderError(f"Erreur du fournisseur IA (code {status}).", code='http_error', status_code=502)

        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) or 'timed out' in str(e.reason).lower():
                logger.warning("Timeout réseau lors de l'appel Gemini.")
                raise IATimeoutError()
            logger.error("Erreur réseau lors de l'appel Gemini : %s", e.reason)
            raise IAUnavailableError("Impossible de joindre le service IA.")

        except TimeoutError:
            logger.warning("Timeout lors de l'appel Gemini.")
            raise IATimeoutError()


def get_default_provider():
    """Factory permettant d'instancier le provider configuré."""
    return GeminiProvider()

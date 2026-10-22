"""Exceptions métier pour le module véhicules."""
from typing import List, Any


class MaintenanceEnConflit(Exception):
    """Levée lorsqu'une maintenance chevauche un ou plusieurs trajets confirmés."""

    def __init__(self, message: str, conflits: List[Any] = None):
        super().__init__(message)
        self.message = message
        self.conflits = conflits or []

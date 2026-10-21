"""Règles d'accès aux données du module Avis et réclamations.

Le module « Transports » n'existe pas encore : une demande de transport publiée tient donc
lieu de prestation. Quand il sera disponible, seules ces fonctions (et la clé étrangère
`demande` des modèles) devront être adaptées pour pointer vers le transport réellement effectué.
"""
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q

from authentification.models import User
from demandes.models import DemandeTransport


def demandes_du_pme(user):
    """Demandes publiées (hors brouillons) créées par ce PME."""
    return DemandeTransport.objects.filter(created_by=user).exclude(statut=DemandeTransport.Statut.BROUILLON)


def demandes_du_destinataire(user):
    """Demandes publiées dont le destinataire désigné correspond à ce compte (nom ou e-mail)."""
    identifiants = [valeur for valeur in (user.full_name, user.email) if valeur]
    condition = Q()
    for valeur in identifiants:
        condition |= Q(destinataire_nom__iexact=valeur) | Q(destinataire_contact__iexact=valeur)
    if not condition:
        return DemandeTransport.objects.none()
    return DemandeTransport.objects.filter(condition).exclude(statut=DemandeTransport.Statut.BROUILLON)


def demandes_reclamables(user):
    """Demandes pour lesquelles cet utilisateur peut déposer une réclamation."""
    if user.role == User.Role.PME:
        return demandes_du_pme(user)
    if user.role == User.Role.DESTINATAIRE:
        return demandes_du_destinataire(user)
    return DemandeTransport.objects.none()


def transporteurs_actifs():
    return get_user_model().objects.filter(role=User.Role.TRANSPORTEUR, is_active=True).order_by('full_name')


def repartition_notes(avis_publies):
    """Nombre d'avis par note (de 5 à 1), avec le pourcentage pour l'affichage des barres."""
    total = avis_publies.count()
    comptes = {note: 0 for note in range(5, 0, -1)}
    for note in avis_publies.values_list('note', flat=True):
        comptes[note] += 1
    return [
        {'note': note, 'nombre': nombre, 'pourcentage': round(nombre * 100 / total) if total else 0}
        for note, nombre in comptes.items()
    ]


def paginer(request, queryset, par_page=10):
    return Paginator(queryset, par_page).get_page(request.GET.get('page'))

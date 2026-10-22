"""Services métier et couche d'adaptation découplée pour le module véhicules."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .exceptions import MaintenanceEnConflit

# ==============================================================================
# COUCHE D'ADAPTATION VERS LE MODULE TRAJETS (DÉCOUPLAGE TOTAL)
# Aucun import direct de modèle : tout passe par apps.get_model.
# Si le coéquipier renomme un champ, modifiez UNIQUEMENT ces constantes.
# ==============================================================================
TRAJET_APP_LABEL = 'gestion_trajets'
TRAJET_MODEL_NAME = 'Trajet'
TRAJET_FIELD_VEHICULE = 'vehicule'          # Immatriculation (CharField) ou FK
TRAJET_FIELD_DATE_DEPART = 'date_depart'
TRAJET_FIELD_DEPART_VILLE = 'depart_ville'
TRAJET_FIELD_ARRIVEE_VILLE = 'arrivee_ville'
TRAJET_FIELD_STATUT = 'statut'

# Statuts considérés comme "actifs / confirmés" bloquant une maintenance
TRAJET_STATUTS_ACTIFS = {'publie', 'en_cours'}

# Fuseau horaire métier de référence
TUNIS_TZ = ZoneInfo("Africa/Tunis")

# Durée estimée par défaut d'un trajet si seule la date de départ est stockée
DUREE_TRAJET_ESTIMEE_HEURES = 6


@dataclass
class TrajetConflitInfo:
    """Représentation simple et découplée d'un trajet en conflit."""
    id: Any
    depart: str
    arrivee: str
    date_debut: datetime
    date_fin: datetime


def _get_trajet_model():
    """Récupère dynamiquement le modèle Trajet sans plantage en cas d'absence."""
    try:
        return apps.get_model(TRAJET_APP_LABEL, TRAJET_MODEL_NAME)
    except (LookupError, ValueError):
        return None


def trajets_actifs_en_conflit(vehicule, date_debut: datetime, date_fin: datetime) -> List[TrajetConflitInfo]:
    """Recherche les trajets confirmés/en cours d'un véhicule qui chevauchent la période donnée.

    Règle de chevauchement strict : debut_A < fin_B ET fin_A > debut_B.
    Une maintenance qui commence exactement à la fin d'un trajet (fin == début) n'est PAS un conflit.
    """
    Trajet = _get_trajet_model()
    if not Trajet or not vehicule:
        return []

    immatriculation = getattr(vehicule, 'immatriculation', str(vehicule)).strip().upper()

    try:
        # Recherche par immatriculation ou FK
        qs = Trajet.objects.filter(
            **{f"{TRAJET_FIELD_STATUT}__in": TRAJET_STATUTS_ACTIFS}
        )

        conflits: List[TrajetConflitInfo] = []
        for t in qs:
            val_veh = getattr(t, TRAJET_FIELD_VEHICULE, None)
            veh_str = getattr(val_veh, 'immatriculation', str(val_veh) if val_veh is not None else '').strip().upper()
            if veh_str != immatriculation:
                continue

            # Dates du trajet
            t_debut = getattr(t, TRAJET_FIELD_DATE_DEPART, None)
            if not t_debut:
                continue
            if timezone.is_naive(t_debut):
                t_debut = timezone.make_aware(t_debut, TUNIS_TZ)
            else:
                t_debut = t_debut.astimezone(TUNIS_TZ)

            # Si le modèle Trajet possède date_fin ou date_arrivee, l'utiliser, sinon estimation
            t_fin = getattr(t, 'date_fin', None) or getattr(t, 'date_arrivee', None)
            if not t_fin:
                t_fin = t_debut + timedelta(hours=DUREE_TRAJET_ESTIMEE_HEURES)
            elif timezone.is_naive(t_fin):
                t_fin = timezone.make_aware(t_fin, TUNIS_TZ)
            else:
                t_fin = t_fin.astimezone(TUNIS_TZ)

            # Conversion de la période demandée dans le fuseau Tunis
            p_debut = date_debut if timezone.is_aware(date_debut) else timezone.make_aware(date_debut, TUNIS_TZ)
            p_debut = p_debut.astimezone(TUNIS_TZ)
            p_fin = date_fin if timezone.is_aware(date_fin) else timezone.make_aware(date_fin, TUNIS_TZ)
            p_fin = p_fin.astimezone(TUNIS_TZ)

            # Règle de chevauchement : p_debut < t_fin ET p_fin > t_debut
            if p_debut < t_fin and p_fin > t_debut:
                conflits.append(
                    TrajetConflitInfo(
                        id=t.pk,
                        depart=getattr(t, TRAJET_FIELD_DEPART_VILLE, 'Départ'),
                        arrivee=getattr(t, TRAJET_FIELD_ARRIVEE_VILLE, 'Arrivée'),
                        date_debut=t_debut,
                        date_fin=t_fin,
                    )
                )

        return conflits
    except Exception:
        # Si une table n'est pas encore créée ou champ manquant, renvoie liste vide sans planter
        return []


def formater_conflit_trajet(conflit: TrajetConflitInfo) -> str:
    """Formate la description d'un trajet en conflit en français au fuseau Africa/Tunis."""
    MOIS_FR = {
        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril', 5: 'mai', 6: 'juin',
        7: 'juillet', 8: 'août', 9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
    }

    d = conflit.date_debut.astimezone(TUNIS_TZ)
    f = conflit.date_fin.astimezone(TUNIS_TZ)

    # Même jour : "le 25 octobre de 8 h à 14 h"
    if d.date() == f.date():
        h_d = f"{d.hour} h{f' {d.minute:02d}' if d.minute else ''}"
        h_f = f"{f.hour} h{f' {f.minute:02d}' if f.minute else ''}"
        return (
            f"le trajet {conflit.depart} → {conflit.arrivee}, "
            f"le {d.day} {MOIS_FR.get(d.month, '')} de {h_d} à {h_f}"
        )
    else:
        # Plusieurs jours : "du 25 octobre 8 h au 27 octobre 14 h"
        h_d = f"{d.hour} h{f' {d.minute:02d}' if d.minute else ''}"
        h_f = f"{f.hour} h{f' {f.minute:02d}' if f.minute else ''}"
        return (
            f"le trajet {conflit.depart} → {conflit.arrivee}, "
            f"du {d.day} {MOIS_FR.get(d.month, '')} {h_d} au {f.day} {MOIS_FR.get(f.month, '')} {h_f}"
        )


def verifier_pas_de_conflit_trajet(vehicule, date_debut: datetime, date_fin: datetime):
    """Vérifie l'absence de conflit de trajet. Si conflit, lève MaintenanceEnConflit et ValidationError."""
    conflits = trajets_actifs_en_conflit(vehicule, date_debut, date_fin)
    if conflits:
        descriptions = [formater_conflit_trajet(c) for c in conflits]
        if len(descriptions) == 1:
            msg = (
                f"Impossible de programmer cette maintenance : le véhicule est affecté au "
                f"{descriptions[0]}. Réaffectez le trajet à un autre véhicule ou choisissez "
                f"une autre période de maintenance."
            )
        else:
            liste_str = " ; ".join(descriptions)
            msg = (
                f"Impossible de programmer cette maintenance : le véhicule est affecté aux trajets suivants : "
                f"{liste_str}. Réaffectez ces trajets à un autre véhicule ou choisissez une autre période."
            )
        raise MaintenanceEnConflit(msg, conflits=conflits)


# ==============================================================================
# SENS 2 & FONCTIONS APPELÉES PAR LE MODULE OFFRES / DEMANDES
# ==============================================================================

def verifier_vehicule_pour_offre(vehicule, date_debut: datetime, date_fin: datetime) -> Tuple[bool, Optional[str]]:
    """Vérifie si un véhicule peut effectuer une offre/trajet sur la période demandée.

    Sens 2 : Un véhicule ayant une maintenance planifiee ou en_cours qui chevauche
    la période est refusé.
    Retourne (True, None) si valide, ou (False, raison_en_français) si refusé.
    """
    if not vehicule:
        return False, "Aucun véhicule spécifié."

    # Vérification statut global
    statut = getattr(vehicule, 'statut', '')
    if statut in {'en_maintenance', 'desactive'}:
        return False, f"Le véhicule n'est pas disponible (statut : {vehicule.get_statut_display() if hasattr(vehicule, 'get_statut_display') else statut})."

    # Vérification des maintenances actives en chevauchement
    from .models import Maintenance
    maintenances = Maintenance.objects.filter(
        vehicule=vehicule,
        statut__in=[Maintenance.Statut.PLANIFIEE, Maintenance.Statut.EN_COURS],
        date_debut__lt=date_fin,
        date_fin__gt=date_debut,
    ).order_by('date_debut')

    m = maintenances.first()
    if m:
        d = m.date_debut.astimezone(TUNIS_TZ)
        f = m.date_fin.astimezone(TUNIS_TZ)
        return False, f"Le véhicule est en maintenance du {d.strftime('%d/%m/%Y %H:%M')} au {f.strftime('%d/%m/%Y %H:%M')}."

    return True, None


def vehicules_compatibles(transporteur, date_debut: datetime, date_fin: datetime, type_vehicule: Optional[str] = None):
    """Retourne le queryset des véhicules actifs du transporteur sans maintenance sur la période."""
    from .models import Vehicule, Maintenance
    qs = Vehicule.objects.filter(transporteur=transporteur, statut=Vehicule.Statut.ACTIF)
    if type_vehicule:
        qs = qs.filter(type_vehicule=type_vehicule)

    # Exclure les véhicules ayant une maintenance planifiée ou en cours sur la période
    vehicules_bloques_ids = Maintenance.objects.filter(
        vehicule__transporteur=transporteur,
        statut__in=[Maintenance.Statut.PLANIFIEE, Maintenance.Statut.EN_COURS],
        date_debut__lt=date_fin,
        date_fin__gt=date_debut,
    ).values_list('vehicule_id', flat=True)

    return qs.exclude(id__in=vehicules_bloques_ids)


def reserver_disponibilite(disponibilite, date_debut: Optional[datetime] = None, date_fin: Optional[datetime] = None):
    """Réserve une disponibilité pour un transport confirmé en vérifiant les maintenances."""
    from .models import Disponibilite
    debut = date_debut or disponibilite.date_debut
    fin = date_fin or disponibilite.date_fin

    valide, raison = verifier_vehicule_pour_offre(disponibilite.vehicule, debut, fin)
    if not valide:
        raise ValidationError(f"Réservation impossible : {raison}")

    with transaction.atomic():
        disponibilite.statut = Disponibilite.Statut.RESERVE
        disponibilite.save(update_fields=['statut'])
    return disponibilite


def liberer_disponibilite(disponibilite):
    """Libère une disponibilité réservée en la remettant disponible."""
    from .models import Disponibilite
    with transaction.atomic():
        disponibilite.statut = Disponibilite.Statut.DISPONIBLE
        disponibilite.save(update_fields=['statut'])
    return disponibilite


# ==============================================================================
# ACTIONS DU CYCLE DE VIE DES MAINTENANCES
# ==============================================================================

def demarrer_maintenance(maintenance):
    """Passe la maintenance en cours et le véhicule en maintenance."""
    from .models import Maintenance, Vehicule
    if maintenance.statut != Maintenance.Statut.PLANIFIEE:
        raise ValidationError("Seule une maintenance planifiée peut être démarrée.")

    # Contrôle de sécurité sur les trajets en cours
    now = timezone.now()
    verifier_pas_de_conflit_trajet(maintenance.vehicule, now, maintenance.date_fin)

    with transaction.atomic():
        maintenance.statut = Maintenance.Statut.EN_COURS
        maintenance.save(update_fields=['statut'])
        vehicule = maintenance.vehicule
        if vehicule.statut == Vehicule.Statut.ACTIF:
            vehicule.statut = Vehicule.Statut.EN_MAINTENANCE
            vehicule.save(update_fields=['statut'])
    return maintenance


def terminer_maintenance(maintenance):
    """Termine une maintenance en cours et réactive le véhicule s'il était en maintenance."""
    from .models import Maintenance, Vehicule
    if maintenance.statut != Maintenance.Statut.EN_COURS:
        raise ValidationError("Seule une maintenance en cours peut être terminée.")

    with transaction.atomic():
        maintenance.statut = Maintenance.Statut.TERMINEE
        maintenance.save(update_fields=['statut'])
        vehicule = maintenance.vehicule
        # Vérifier si une autre maintenance est encore en cours pour ce véhicule
        autres_en_cours = Maintenance.objects.filter(
            vehicule=vehicule,
            statut=Maintenance.Statut.EN_COURS,
        ).exclude(pk=maintenance.pk).exists()

        if not autres_en_cours and vehicule.statut == Vehicule.Statut.EN_MAINTENANCE:
            vehicule.statut = Vehicule.Statut.ACTIF
            vehicule.save(update_fields=['statut'])
    return maintenance


def annuler_maintenance(maintenance):
    """Annule une maintenance planifiée."""
    from .models import Maintenance, Vehicule
    if maintenance.statut not in {Maintenance.Statut.PLANIFIEE, Maintenance.Statut.EN_COURS}:
        raise ValidationError("Cette maintenance ne peut pas être annulée.")

    with transaction.atomic():
        maintenance.statut = Maintenance.Statut.ANNULEE
        maintenance.save(update_fields=['statut'])
        vehicule = maintenance.vehicule
        autres_en_cours = Maintenance.objects.filter(
            vehicule=vehicule,
            statut=Maintenance.Statut.EN_COURS,
        ).exclude(pk=maintenance.pk).exists()

        if not autres_en_cours and vehicule.statut == Vehicule.Statut.EN_MAINTENANCE:
            vehicule.statut = Vehicule.Statut.ACTIF
            vehicule.save(update_fields=['statut'])
    return maintenance


def verifier_passage_manuel_en_maintenance(vehicule):
    """Vérifie si un véhicule peut être passé manuellement en statut maintenance (bouton rapide)."""
    now = timezone.now()
    fin_horizon = now + timedelta(days=365)
    conflits = trajets_actifs_en_conflit(vehicule, now, fin_horizon)
    if conflits:
        descriptions = [formater_conflit_trajet(c) for c in conflits]
        msg = (
            f"Impossible de passer ce véhicule en maintenance : il est affecté au {descriptions[0]}. "
            f"Veuillez réaffecter le trajet avant de changer son statut."
        )
        raise ValidationError(msg)

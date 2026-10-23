"""Règles transparentes et déterministes d'évaluation du risque de maintenance.

Ce module implémente :
1. L'extraction stricte et minimisée des variables explicatives d'un véhicule
   (AUCUNE donnée à caractère personnel : ni immatriculation, ni nom, ni texte libre).
2. Un système de calcul de score à règles (0-100), transparent et explicable,
   servant de baseline robuste et de garde-fou déterministe.
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from django.utils import timezone

from vehicules.models import Maintenance, Vehicule

TUNIS_TZ = ZoneInfo("Africa/Tunis")

# ==============================================================================
# SEUILS ET CONSTANTES DES RÈGLES MÉTIER (INDICATIF DE MAINTENANCE)
# ==============================================================================
# Âge du véhicule (années)
SEUIL_AGE_ANCIEN = 10
SEUIL_AGE_MOYEN = 5

# Kilométrage total
SEUIL_KM_ELEVE = 250_000
SEUIL_KM_MOYEN = 120_000

# Kilométrage depuis le dernier entretien périodique
SEUIL_KM_ENTRETIEN_DEPASSE = 30_000
SEUIL_KM_ENTRETIEN_ATTENTION = 15_000

# Jours écoulés depuis la dernière maintenance terminée
SEUIL_JOURS_MAINTENANCE_CRITIQUE = 365
SEUIL_JOURS_MAINTENANCE_ATTENTION = 180

# Pannes / réparations sur les 12 derniers mois
SEUIL_REPARATIONS_CRITIQUE = 3
SEUIL_REPARATIONS_ATTENTION = 1

# Plafond maximum du score si des données fondamentales sont manquantes
PLAFOND_DONNEES_INSUFFISANTES = 40


def calculer_variables(vehicule: Vehicule, date_reference: Optional[date] = None) -> Dict[str, Any]:
    """Extrait les variables explicatives sans AUCUNE donnée identifiante ni personnelle.

    Args:
        vehicule: Instance du modèle Vehicule.
        date_reference: Date pivot pour les calculs d'intervalles (utile pour les tests et le rejeu).
                        Par défaut date du jour en Tunisie.

    Returns:
        Dictionnaire contenant les variables standardisées et la liste des données manquantes.
    """
    if date_reference is None:
        date_reference = timezone.now().astimezone(TUNIS_TZ).date()
    elif isinstance(date_reference, datetime):
        date_reference = date_reference.date()

    donnees_manquantes: List[str] = []

    # 1. Âge du véhicule
    age_annees: Optional[int] = None
    if vehicule.annee:
        age_annees = max(0, date_reference.year - vehicule.annee)
    else:
        donnees_manquantes.append('annee')

    # 2. Kilométrage actuel
    kilometrage: Optional[int] = vehicule.kilometrage
    if kilometrage is None:
        donnees_manquantes.append('kilometrage')

    # 3. Maintenances terminées
    maintenances_terminees = list(
        vehicule.maintenances.filter(
            statut=Maintenance.Statut.TERMINEE,
        ).order_by('-date_fin')
    )

    # 4. Jours depuis dernière maintenance terminée
    jours_depuis_derniere_maintenance: Optional[int] = None
    if maintenances_terminees:
        derniere = maintenances_terminees[0]
        # date_fin en date
        date_derniere = derniere.date_fin.astimezone(TUNIS_TZ).date() if timezone.is_aware(derniere.date_fin) else derniere.date_fin.date()
        jours_depuis_derniere_maintenance = max(0, (date_reference - date_derniere).days)
    else:
        donnees_manquantes.append('historique_maintenance')

    # 5. Période des 12 derniers mois
    date_12m_avant = date_reference - timedelta(days=365)
    maintenances_12m = [
        m for m in maintenances_terminees
        if (m.date_fin.astimezone(TUNIS_TZ).date() if timezone.is_aware(m.date_fin) else m.date_fin.date()) >= date_12m_avant
    ]

    nb_reparations_12m = sum(1 for m in maintenances_12m if m.motif == Maintenance.Motif.REPARATION)
    nb_entretiens_12m = sum(1 for m in maintenances_12m if m.motif == Maintenance.Motif.ENTRETIEN_PERIODIQUE)

    # 6. Kilomètres depuis le dernier entretien périodique
    km_depuis_dernier_entretien: Optional[int] = None
    derniers_entretiens = [
        m for m in maintenances_terminees
        if m.motif == Maintenance.Motif.ENTRETIEN_PERIODIQUE and m.kilometrage_releve is not None
    ]
    if derniers_entretiens and kilometrage is not None:
        dernier_km_entretien = derniers_entretiens[0].kilometrage_releve
        if kilometrage >= dernier_km_entretien:
            km_depuis_dernier_entretien = kilometrage - dernier_km_entretien
        else:
            # Donnée incohérente dans le relevé
            km_depuis_dernier_entretien = None

    # 7. Présence d'une maintenance planifiée à venir
    maintenance_planifiee_a_venir = vehicule.maintenances.filter(
        statut=Maintenance.Statut.PLANIFIEE,
        date_debut__gte=timezone.now(),
    ).exists()

    return {
        'age_annees': age_annees,
        'kilometrage': kilometrage,
        'type_vehicule': vehicule.type_vehicule,
        'jours_depuis_derniere_maintenance': jours_depuis_derniere_maintenance,
        'nb_reparations_12m': nb_reparations_12m,
        'nb_entretiens_12m': nb_entretiens_12m,
        'km_depuis_dernier_entretien': km_depuis_dernier_entretien,
        'maintenance_planifiee_a_venir': maintenance_planifiee_a_venir,
        'donnees_manquantes': donnees_manquantes,
    }


def score_regles(variables: Dict[str, Any]) -> Dict[str, Any]:
    """Calcule un score déterministe (0-100) et des facteurs explicatifs.

    Règles additives pondérées avec explications claires et gestion rigoureuse
    des données manquantes (plafonnement et facteur explicatif).
    """
    points = 0
    facteurs: List[Dict[str, Any]] = []

    age = variables.get('age_annees')
    km = variables.get('kilometrage')
    jours_maint = variables.get('jours_depuis_derniere_maintenance')
    nb_rep = variables.get('nb_reparations_12m', 0)
    nb_ent = variables.get('nb_entretiens_12m', 0)
    km_entretien = variables.get('km_depuis_dernier_entretien')
    maint_planifiee = variables.get('maintenance_planifiee_a_venir', False)
    manquantes = variables.get('donnees_manquantes', [])

    # 1. Règle d'ancienneté / âge
    if age is not None:
        if age >= SEUIL_AGE_ANCIEN:
            points += 25
            facteurs.append({
                'facteur': 'age_eleve',
                'impact': 'hausse',
                'poids': 25,
                'explication': f"Véhicule ancien ({age} ans), composants d'usure plus sollicités.",
            })
        elif age >= SEUIL_AGE_MOYEN:
            points += 15
            facteurs.append({
                'facteur': 'age_moyen',
                'impact': 'hausse',
                'poids': 15,
                'explication': f"Véhicule d'âge intermédiaire ({age} ans).",
            })
        elif age <= 2:
            points -= 10
            facteurs.append({
                'facteur': 'vehicule_recent',
                'impact': 'baisse',
                'poids': -10,
                'explication': f"Véhicule récent ({age} an(s)), fiabilité initiale plus élevée.",
            })

    # 2. Règle du kilométrage total
    if km is not None:
        if km >= SEUIL_KM_ELEVE:
            points += 25
            facteurs.append({
                'facteur': 'kilometrage_eleve',
                'impact': 'hausse',
                'poids': 25,
                'explication': f"Kilométrage important ({km:,} km) augmentant le besoin de révisions.",
            })
        elif km >= SEUIL_KM_MOYEN:
            points += 15
            facteurs.append({
                'facteur': 'kilometrage_moyen',
                'impact': 'hausse',
                'poids': 15,
                'explication': f"Kilométrage moyen ({km:,} km).",
            })
        elif km < 50_000:
            points -= 10
            facteurs.append({
                'facteur': 'faible_kilometrage',
                'impact': 'baisse',
                'poids': -10,
                'explication': f"Faible kilométrage ({km:,} km).",
            })

    # 3. Règle du kilométrage depuis le dernier entretien
    if km_entretien is not None:
        if km_entretien >= SEUIL_KM_ENTRETIEN_DEPASSE:
            points += 25
            facteurs.append({
                'facteur': 'echeance_km_depassee',
                'impact': 'hausse',
                'poids': 25,
                'explication': f"{km_entretien:,} km parcourus depuis le dernier entretien périodique.",
            })
        elif km_entretien >= SEUIL_KM_ENTRETIEN_ATTENTION:
            points += 15
            facteurs.append({
                'facteur': 'echeance_km_proche',
                'impact': 'hausse',
                'poids': 15,
                'explication': f"Proche de l'échéance de vidange/révision ({km_entretien:,} km).",
            })

    # 4. Règle du temps écoulé depuis la dernière maintenance
    if jours_maint is not None:
        if jours_maint >= SEUIL_JOURS_MAINTENANCE_CRITIQUE:
            points += 25
            facteurs.append({
                'facteur': 'maintenance_ancienne',
                'impact': 'hausse',
                'poids': 25,
                'explication': f"Aucun passage en atelier depuis plus d'un an ({jours_maint} jours).",
            })
        elif jours_maint >= SEUIL_JOURS_MAINTENANCE_ATTENTION:
            points += 10
            facteurs.append({
                'facteur': 'delai_maintenance_moyen',
                'impact': 'hausse',
                'poids': 10,
                'explication': f"Dernière maintenance il y a plus de 6 mois ({jours_maint} jours).",
            })
        elif jours_maint <= 45:
            points -= 15
            facteurs.append({
                'facteur': 'maintenance_recente',
                'impact': 'baisse',
                'poids': -15,
                'explication': f"Maintenance effectuée récemment il y a {jours_maint} jours.",
            })

    # 5. Règle de répétition des pannes / réparations
    if nb_rep >= SEUIL_REPARATIONS_CRITIQUE:
        points += 30
        facteurs.append({
            'facteur': 'reparations_frequentes',
            'impact': 'hausse',
            'poids': 30,
            'explication': f"{nb_rep} réparations curatives sur les 12 derniers mois (vulnérabilité récurrente).",
        })
    elif nb_rep >= SEUIL_REPARATIONS_ATTENTION:
        points += 15
        facteurs.append({
            'facteur': 'reparations_recentes',
            'impact': 'hausse',
            'poids': 15,
            'explication': f"{nb_rep} réparation(s) constatée(s) au cours de l'année écoulée.",
        })

    # 6. Atténuation si maintenance planifiée
    if maint_planifiee:
        points -= 10
        facteurs.append({
            'facteur': 'maintenance_deja_planifiee',
            'impact': 'baisse',
            'poids': -10,
            'explication': "Un créneau de maintenance est déjà programmé à court terme.",
        })

    # 7. Gestion des données manquantes
    if manquantes:
        facteurs.append({
            'facteur': 'donnees_insuffisantes',
            'impact': 'baisse',
            'poids': 0,
            'explication': f"Données partielles ({', '.join(manquantes)}) : analyse basée sur les données connues.",
        })
        # Si kilométrage et historique manquent complètement, on borne le score
        if 'kilometrage' in manquantes and 'historique_maintenance' in manquantes:
            points = min(points, PLAFOND_DONNEES_INSUFFISANTES)

    # Normalisation entre 0 et 100
    score_normalise = max(0, min(100, points))

    # Attribution du niveau de risque
    if score_normalise >= 60:
        niveau = 'eleve'
    elif score_normalise >= 30:
        niveau = 'moyen'
    else:
        niveau = 'faible'

    return {
        'score': score_normalise,
        'niveau': niveau,
        'facteurs': facteurs,
    }

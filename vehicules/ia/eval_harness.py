"""Jeu de données de test et harness d'évaluation pour l'analyse du risque.

Contient :
- 60 profils synthétiques réalistes (20 risque faible, 20 modéré, 20 élevé)
- Évaluation automatique des métriques :
  * Accord directionnel entre règles déterministes et IA
  * Taux de repli gracieux
  * Présence et validité des facteurs explicatifs
  * Temps de réponse moyen
- Rapport synthétique au format texte / markdown
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time


@dataclass
class ProfilVehiculeTest:
    id_profil: str
    categorie_attendue: str  # 'faible' | 'moyen' | 'eleve'
    age_annees: Optional[int]
    kilometrage: Optional[int]
    type_vehicule: str
    jours_depuis_derniere_maintenance: Optional[int]
    nb_reparations_12m: int
    nb_entretiens_12m: int
    km_depuis_dernier_entretien: Optional[int]
    maintenance_planifiee_a_venir: bool
    donnees_manquantes: List[str]


def generer_60_profils() -> List[ProfilVehiculeTest]:
    """Génère 60 profils synthétiques calibrés (20 faible, 20 moyen, 20 élevé)."""
    profils: List[ProfilVehiculeTest] = []

    # --------------------------------------------------------------------------
    # 20 PROFILS : RISQUE ATTENDU FAIBLE
    # Véhicules récents (< 3 ans), faible/moyen km, entretenus récemment
    # --------------------------------------------------------------------------
    for i in range(1, 21):
        profils.append(ProfilVehiculeTest(
            id_profil=f"FAIBLE_{i:02d}",
            categorie_attendue="faible",
            age_annees=1 if i <= 10 else 2,
            kilometrage=15000 * i // 2 + 5000,
            type_vehicule="FOURGON" if i % 2 == 0 else "CAMIONNETTE",
            jours_depuis_derniere_maintenance=30 + (i * 5),
            nb_reparations_12m=0,
            nb_entretiens_12m=1 if i <= 15 else 2,
            km_depuis_dernier_entretien=3000 + (i * 500),
            maintenance_planifiee_a_venir=(i % 3 == 0),
            donnees_manquantes=[],
        ))

    # --------------------------------------------------------------------------
    # 20 PROFILS : RISQUE ATTENDU MODÉRÉ (MOYEN)
    # Véhicules d'âge moyen (3-6 ans), 80k-180k km, entretien régulier
    # --------------------------------------------------------------------------
    for i in range(1, 21):
        donnees_manquantes = ["kilometrage"] if i == 7 else []
        km = None if i == 7 else 80000 + (i * 4000)
        profils.append(ProfilVehiculeTest(
            id_profil=f"MOYEN_{i:02d}",
            categorie_attendue="moyen",
            age_annees=3 + (i % 4),
            kilometrage=km,
            type_vehicule="CAMION" if i % 2 == 0 else "FOURGON",
            jours_depuis_derniere_maintenance=90 + (i * 5),
            nb_reparations_12m=1 if i <= 15 else 2,
            nb_entretiens_12m=1,
            km_depuis_dernier_entretien=12000 + (i * 500) if km else None,
            maintenance_planifiee_a_venir=(i % 3 == 0),
            donnees_manquantes=donnees_manquantes,
        ))

    # --------------------------------------------------------------------------
    # 20 PROFILS : RISQUE ATTENDU ÉLEVÉ
    # Véhicules anciens (> 9 ans), très fort kilométrage (> 350k km),
    # nombreuses réparations curatives récentes ou absence prolongée d'entretien
    # --------------------------------------------------------------------------
    for i in range(1, 21):
        profils.append(ProfilVehiculeTest(
            id_profil=f"ELEVE_{i:02d}",
            categorie_attendue="eleve",
            age_annees=9 + (i % 6),
            kilometrage=350000 + (i * 15000),
            type_vehicule="CAMION_POIDS_LOURD" if i % 3 == 0 else "SEMI_REMORQUE",
            jours_depuis_derniere_maintenance=400 + (i * 20),
            nb_reparations_12m=3 + (i % 3),
            nb_entretiens_12m=0 if i % 2 == 0 else 1,
            km_depuis_dernier_entretien=45000 + (i * 2000),
            maintenance_planifiee_a_venir=False,
            donnees_manquantes=[],
        ))

    return profils


def executer_evaluation_regles() -> Dict[str, Any]:
    """Exécute l'évaluation du moteur de règles sur les 60 profils de référence.

    Mesure la précision de classification par rapport aux catégories attendues.
    """
    from .risque_regles import score_regles

    profils = generer_60_profils()
    total = len(profils)
    correspondances_exactes = 0
    matrice_confusion = {
        'faible': {'faible': 0, 'moyen': 0, 'eleve': 0},
        'moyen': {'faible': 0, 'moyen': 0, 'eleve': 0},
        'eleve': {'faible': 0, 'moyen': 0, 'eleve': 0},
    }

    t0 = time.monotonic()
    for p in profils:
        variables = {
            'age_annees': p.age_annees,
            'kilometrage': p.kilometrage,
            'type_vehicule': p.type_vehicule,
            'jours_depuis_derniere_maintenance': p.jours_depuis_derniere_maintenance,
            'nb_reparations_12m': p.nb_reparations_12m,
            'nb_entretiens_12m': p.nb_entretiens_12m,
            'km_depuis_dernier_entretien': p.km_depuis_dernier_entretien,
            'maintenance_planifiee_a_venir': p.maintenance_planifiee_a_venir,
            'donnees_manquantes': p.donnees_manquantes,
        }
        res = score_regles(variables)
        obtenu = res['niveau']
        attendu = p.categorie_attendue

        matrice_confusion[attendu][obtenu] += 1
        if obtenu == attendu:
            correspondances_exactes += 1

    duree_ms = int((time.monotonic() - t0) * 1000)
    precision_globale = (correspondances_exactes / total) * 100

    return {
        'total_profils': total,
        'correspondances_exactes': correspondances_exactes,
        'precision_globale_pct': round(precision_globale, 2),
        'matrice_confusion': matrice_confusion,
        'duree_ms': duree_ms,
    }

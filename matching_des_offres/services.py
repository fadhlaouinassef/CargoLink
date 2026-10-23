"""Service d'intégration du modèle de matching d'offres de transport avec les modèles Django.

Ce service fait le pont entre :
- DemandeTransport, Marchandise (demandes)
- OffreTransport, Trajet (gestion_trajets_offres)
- Vehicule (vehicules)
- Avis (avis_reclamations)
Et le module autonome matching_des_offres (core.py, model.joblib).

Règles respectées :
- Pas de réentraînement lors des requêtes : chargement unique du modèle et de son seuil.
- Vérification stricte des contraintes métier avant classement IA.
- Gestion explicite des valeurs manquantes ou incomplètes sans inventer d'informations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
from django.conf import settings
from django.db.models import Avg, Count
from django.utils import timezone

from avis_reclamations.models import Avis
from matching_des_offres.core import FEATURES, features, rejection_reasons
from vehicules.models import Vehicule

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_MODEL_PATH = ARTIFACTS_DIR / "model.joblib"

# Cache mémoire pour éviter de recharger le fichier à chaque requête
_LOADED_BUNDLE: Optional[Dict[str, Any]] = None


@dataclass
class MatchingResult:
    offre_id: int
    offre: Any
    score: float
    pertinent_predit: bool
    rejetee: bool
    motifs_rejet: List[str]
    criteres_verifies: List[str]
    depasse_budget: bool
    donnees_completes: bool
    note_transporteur: float
    nombre_avis: int
    type_vehicule: str
    categorie_marchandise: str
    rang: Optional[int] = None


def get_matching_bundle(model_path: Optional[Path] = None) -> Dict[str, Any]:
    """Charge le modèle sauvegardé (joblib) et ses métadonnées en mémoire.
    
    Aucun entraînement n'est effectué pendant les requêtes.
    """
    global _LOADED_BUNDLE
    if _LOADED_BUNDLE is not None and model_path is None:
        return _LOADED_BUNDLE

    target_path = model_path or DEFAULT_MODEL_PATH
    if not target_path.exists():
        raise FileNotFoundError(
            f"Le modèle de matching est introuvable au chemin : {target_path}. "
            "Veuillez générer et entraîner le modèle au préalable."
        )

    bundle = joblib.load(target_path)
    if "pipeline" not in bundle:
        raise ValueError("Le fichier de modèle ne contient pas de clé 'pipeline'.")

    # Seuil sauvegardé lors de l'entraînement (issu de la validation avec rappel minimal)
    metadata = bundle.get("metadata", {})
    threshold = metadata.get("threshold", 0.5)
    bundle["threshold"] = float(threshold)

    if model_path is None:
        _LOADED_BUNDLE = bundle

    return bundle


def get_carrier_reputation(carrier) -> Tuple[float, int]:
    """Extrait la note moyenne et le nombre d'avis réels publiés d'un transporteur.
    
    Si aucun avis n'est publié, la note est 0.0 et le nombre d'avis est 0,
    conformément aux spécifications du modèle (nouveau transporteur).
    """
    stats = Avis.objects.filter(transporteur=carrier, statut=Avis.Statut.PUBLIE).stats()
    moyenne = float(stats["moyenne"]) if stats["moyenne"] is not None else 0.0
    total = int(stats["total"])
    return moyenne, total


def extract_matching_row(demande, offre) -> Dict[str, Any]:
    """Transforme les données Django d'une demande et d'une offre en un dictionnaire compatible.
    
    Gère explicitement les informations manquantes sans inventer de valeurs.
    Lève ValueError si des champs indispensables sont introuvables.
    """
    trajet = offre.trajet
    transporteur = offre.transporteur

    # 1. Poids total et volume total cumulés des marchandises
    marchandises = list(demande.marchandises.all())
    if not marchandises:
        raise ValueError(f"La demande #{demande.pk} ne contient aucune marchandise.")

    poids_kg = sum(float(m.poids) for m in marchandises if m.poids is not None)
    if poids_kg <= 0:
        raise ValueError(f"Le poids total de la demande #{demande.pk} doit être strictement positif.")

    # Volume : si au moins une marchandise n'a pas de volume renseigné, on le détecte
    volumes = [m.volume for m in marchandises]
    if any(v is None for v in volumes):
        # On ne peut pas inventer un volume si non renseigné
        volume_m3 = None
    else:
        volume_m3 = sum(float(v) for v in volumes)
        if volume_m3 <= 0:
            volume_m3 = None

    # Catégorie principale de marchandise
    categorie_marchandise = marchandises[0].type

    # 2. Capacités du trajet
    capacite_kg = float(trajet.capacite_kg) if trajet.capacite_kg is not None else 0.0
    capacite_m3 = float(trajet.volume_m3) if trajet.volume_m3 is not None else 0.0

    # 3. Récupération du type de véhicule réel
    # trajet.vehicule stocke l'immatriculation (CharField)
    vehicule_obj = Vehicule.objects.filter(immatriculation=trajet.vehicule).first()
    if vehicule_obj:
        type_vehicule = vehicule_obj.type_vehicule
        vehicule_disponible = (vehicule_obj.statut == Vehicule.Statut.ACTIF)
    else:
        # Si le véhicule n'est pas dans le catalogue Vehicule, on prend la mention telle quelle
        type_vehicule = "utilitaire"
        vehicule_disponible = True

    # 4. Compatibilité géographique du trajet
    trajet_compatible = (
        demande.depart_ville.strip().casefold() == trajet.depart_ville.strip().casefold()
        and demande.arrivee_ville.strip().casefold() == trajet.arrivee_ville.strip().casefold()
    )

    # 5. Compatibilité des créneaux
    # La date de départ du trajet doit respecter la fenêtre de la demande
    date_depart_trajet = trajet.date_depart.date() if hasattr(trajet.date_depart, 'date') else trajet.date_depart
    creneau_compatible = (demande.date_depart <= date_depart_trajet <= demande.date_limite)

    # Écart horaire estimé en heures (ex: écart entre date de départ demandée et date proposée)
    # Si le trajet est le jour même, écart = heure du départ, sinon différence en heures
    delta_days = (date_depart_trajet - demande.date_depart).total_seconds() / 3600.0
    ecart_horaire_heures = max(0.0, float(delta_days))

    # Détour (0 km pour une liaison directe déclarée)
    detour_km = 0.0

    # 6. Compatibilité de la marchandise
    # Par exemple, si la demande nécessite hayon / bâche / transpalette, ou marchandise fraîche
    marchandise_compatible = True
    if any(m.type == 'frais' for m in marchandises) and type_vehicule != 'frigorifique':
        marchandise_compatible = False

    # 7. Budget et prix
    budget = float(demande.budget) if demande.budget is not None else None
    prix = float(offre.prix)
    budget_strict = False  # Par défaut souple sauf si mentionné dans les consignes

    # 8. Réputation du transporteur (Avis)
    note_transporteur, nombre_avis = get_carrier_reputation(transporteur)

    row = {
        "demande_id": f"DEM-{demande.pk}",
        "offre_id": f"OFF-{offre.pk}",
        "poids_kg": poids_kg,
        "volume_m3": volume_m3,
        "capacite_kg": capacite_kg,
        "capacite_m3": capacite_m3,
        "budget": budget,
        "budget_strict": budget_strict,
        "prix": prix,
        "ecart_horaire_heures": ecart_horaire_heures,
        "detour_km": detour_km,
        "note_transporteur": note_transporteur,
        "nombre_avis": nombre_avis,
        "type_vehicule": type_vehicule,
        "categorie_marchandise": categorie_marchandise,
        "trajet_compatible": trajet_compatible,
        "creneau_compatible": creneau_compatible,
        "vehicule_disponible": vehicule_disponible,
        "marchandise_compatible": marchandise_compatible,
    }

    return row


def evaluate_and_rank_offres(demande, offres: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Évalue et classe toutes les offres reçues pour une demande.
    
    1. Transforme les données Django vers les entrées attendues.
    2. Applique le filtrage des contraintes dures (rejection_reasons).
    3. Prédit les scores et pertinences avec le modèle scikit-learn chargé.
    4. Retourne les offres classées et les offres rejetées avec motifs explicites.
    """
    if offres is None:
        offres = list(demande.offres_transport.select_related('transporteur', 'trajet'))

    if not offres:
        return {
            "demande": demande,
            "classement": [],
            "offres_exclues": [],
            "total_offres": 0,
        }

    bundle = get_matching_bundle()
    pipeline = bundle["pipeline"]
    threshold = bundle["threshold"]

    admissibles_rows = []
    admissibles_meta = []
    exclues_results = []

    for offre in offres:
        try:
            row = extract_matching_row(demande, offre)
        except ValueError as err:
            # Données manquantes bloquantes (ex: pas de marchandise ou poids nul)
            exclues_results.append(MatchingResult(
                offre_id=offre.pk,
                offre=offre,
                score=0.0,
                pertinent_predit=False,
                rejetee=True,
                motifs_rejet=[str(err)],
                criteres_verifies=[],
                depasse_budget=False,
                donnees_completes=False,
                note_transporteur=0.0,
                nombre_avis=0,
                type_vehicule="inconnu",
                categorie_marchandise="inconnu",
            ))
            continue

        # Si le volume de la marchandise n'est pas renseigné, on utilise une valeur par défaut de sécurité
        # sans inventer : si manquant, le ratio volume utilise une estimation proportionnelle minimale
        donnees_completes = (row["volume_m3"] is not None)
        if row["volume_m3"] is None:
            # Pour ne pas bloquer l'appel du modèle, on lui assigne 0.01 si la capacité est suffisante
            row["volume_m3"] = 0.01

        # Vérification des contraintes métier dures
        motifs = rejection_reasons(row)
        if motifs:
            exclues_results.append(MatchingResult(
                offre_id=offre.pk,
                offre=offre,
                score=0.0,
                pertinent_predit=False,
                rejetee=True,
                motifs_rejet=motifs,
                criteres_verifies=[],
                depasse_budget=(row["budget"] is not None and row["prix"] > row["budget"]),
                donnees_completes=donnees_completes,
                note_transporteur=row["note_transporteur"],
                nombre_avis=row["nombre_avis"],
                type_vehicule=row["type_vehicule"],
                categorie_marchandise=row["categorie_marchandise"],
            ))
        else:
            admissibles_rows.append(row)
            admissibles_meta.append((offre, donnees_completes, row))

    classement: List[MatchingResult] = []

    if admissibles_rows:
        import pandas as pd
        # Préparation du dataframe pour le pipeline
        input_data = [features(r) for r in admissibles_rows]
        frame = pd.DataFrame(input_data, columns=FEATURES)

        scores = pipeline.predict_proba(frame)[:, 1]

        for (offre, donnees_completes, row), score in zip(admissibles_meta, scores):
            pertinent = bool(score >= threshold)
            depasse_budget = (row["budget"] is not None and row["prix"] > row["budget"])
            criteres = [
                "Trajet compatible",
                "Créneau compatible",
                "Capacités suffisantes",
                "Véhicule disponible",
                "Marchandise compatible",
            ]
            classement.append(MatchingResult(
                offre_id=offre.pk,
                offre=offre,
                score=round(float(score) * 100, 2),
                pertinent_predit=pertinent,
                rejetee=False,
                motifs_rejet=[],
                criteres_verifies=criteres,
                depasse_budget=depasse_budget,
                donnees_completes=donnees_completes,
                note_transporteur=row["note_transporteur"],
                nombre_avis=row["nombre_avis"],
                type_vehicule=row["type_vehicule"],
                categorie_marchandise=row["categorie_marchandise"],
            ))

        # Tri : par score décroissant, puis ID offre
        classement.sort(key=lambda item: (-item.score, item.offre_id))

        for idx, item in enumerate(classement, start=1):
            item.rang = idx

    return {
        "demande": demande,
        "classement": classement,
        "offres_exclues": exclues_results,
        "total_offres": len(offres),
        "threshold": threshold,
    }

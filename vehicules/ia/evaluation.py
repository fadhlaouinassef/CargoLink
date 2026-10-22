"""Logique d'évaluation et de comparaison pour l'assistant IA."""
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple


def normalize_zone(val: Optional[str]) -> Optional[str]:
    """Normalise une chaîne de zone (sans accents, sans casse, espaces nettoyés)."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    # Suppression accents (NFD decomposition)
    nfd = unicodedata.normalize('NFD', val_str)
    no_accents = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    lowered = no_accents.lower()
    # Nettoyage de la ponctuation ou prépositions éventuelles
    cleaned = re.sub(r'[\s\-_]+', ' ', lowered).strip()
    return cleaned or None


def compare_zone(obtenu: Optional[str], attendu: Optional[str]) -> bool:
    norm_obt = normalize_zone(obtenu)
    norm_att = normalize_zone(attendu)
    if norm_att is None:
        return norm_obt is None
    if norm_obt is None:
        return False
    return norm_obt == norm_att


def compare_date(obtenu: Optional[str], attendu: Optional[str]) -> bool:
    if attendu is None:
        return obtenu is None
    if obtenu is None:
        return False
    # Comparaison stricte ISO minute (YYYY-MM-DDTHH:MM)
    obt_str = str(obtenu).strip()
    att_str = str(attendu).strip()
    return obt_str == att_str


def compare_type_vehicule(obtenu: Optional[str], attendu: Optional[str]) -> bool:
    if attendu is None:
        return obtenu is None
    if obtenu is None:
        return False
    return str(obtenu).strip().lower() == str(attendu).strip().lower()


def evaluate_phrase_result(
    attendu: Dict[str, Any],
    champs_obtenus: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare les champs obtenus avec les champs attendus.

    Renvoie un dictionnaire avec le statut de chaque champ, l'exactitude globale,
    et la détection d'éventuelles hallucinations.
    """
    zd_match = compare_zone(champs_obtenus.get("zone_depart"), attendu.get("zone_depart"))
    za_match = compare_zone(champs_obtenus.get("zone_arrivee"), attendu.get("zone_arrivee"))
    dd_match = compare_date(champs_obtenus.get("date_debut"), attendu.get("date_debut"))
    df_match = compare_date(champs_obtenus.get("date_fin"), attendu.get("date_fin"))
    tv_match = compare_type_vehicule(champs_obtenus.get("type_vehicule"), attendu.get("type_vehicule"))

    global_match = zd_match and za_match and dd_match and df_match and tv_match

    # Détection d'hallucinations : l'attendu est null mais une valeur non nulle a été extraite
    hallucination_fields = []
    for k in ["zone_depart", "zone_arrivee", "date_debut", "date_fin", "type_vehicule"]:
        if attendu.get(k) is None and champs_obtenus.get(k) is not None:
            hallucination_fields.append(k)

    return {
        "global_match": global_match,
        "matches": {
            "zone_depart": zd_match,
            "zone_arrivee": za_match,
            "date_debut": dd_match,
            "date_fin": df_match,
            "type_vehicule": tv_match,
        },
        "has_hallucination": len(hallucination_fields) > 0,
        "hallucination_fields": hallucination_fields,
    }

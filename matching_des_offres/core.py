"""Filtrage métier et variables disponibles avant la décision."""
import math

NUMERIC = ["ratio_prix_budget", "budget_absent", "ecart_horaire_heures",
           "detour_km", "ratio_poids", "ratio_volume", "note_transporteur", "nombre_avis"]
CATEGORICAL = ["type_vehicule", "categorie_marchandise"]
FEATURES = NUMERIC + CATEGORICAL
POSITIVE = ["poids_kg", "volume_m3", "capacite_kg", "capacite_m3", "prix"]


def validate(row):
    for key in POSITIVE + ["ecart_horaire_heures", "detour_km", "note_transporteur", "nombre_avis"]:
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} doit être un nombre fini")
        if value < 0 or (key in POSITIVE and value == 0):
            raise ValueError(f"{key} hors limites")
    if not 0 <= row["note_transporteur"] <= 5:
        raise ValueError("note_transporteur doit être entre 0 et 5")
    if row["budget"] is not None:
        value = row["budget"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("budget doit être positif ou null")
    for key in ["trajet_compatible", "creneau_compatible", "vehicule_disponible", "marchandise_compatible", "budget_strict"]:
        if type(row[key]) is not bool:
            raise ValueError(f"{key} doit être un booléen")
    if row["budget_strict"] and row["budget"] is None:
        raise ValueError("Un budget strict exige un montant")
    for key in ["demande_id", "offre_id", "type_vehicule", "categorie_marchandise"]:
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError(f"{key} doit être une chaîne non vide")


def rejection_reasons(row):
    validate(row)
    reasons = []
    if row["poids_kg"] > row["capacite_kg"]:
        reasons.append("Capacité en poids insuffisante")
    if row["volume_m3"] > row["capacite_m3"]:
        reasons.append("Capacité en volume insuffisante")
    for key, message in [("trajet_compatible", "Trajet incompatible"),
                         ("creneau_compatible", "Créneau incompatible"),
                         ("vehicule_disponible", "Véhicule indisponible"),
                         ("marchandise_compatible", "Marchandise incompatible")]:
        if not row[key]:
            reasons.append(message)
    if row["budget_strict"] and row["prix"] > row["budget"]:
        reasons.append("Budget strict dépassé")
    return reasons


def features(row):
    validate(row)
    return dict(zip(NUMERIC, [
        row["prix"] / row["budget"] if row["budget"] else 1.0,
        int(row["budget"] is None), row["ecart_horaire_heures"], row["detour_km"],
        row["poids_kg"] / row["capacite_kg"], row["volume_m3"] / row["capacite_m3"],
        row["note_transporteur"], row["nombre_avis"],
    ])) | {key: row[key] for key in CATEGORICAL}


def baseline(frame):
    """Référence fixe, sans apprentissage ; scores de classement uniquement."""
    return (0.55 * (1 - frame.ratio_prix_budget / 2).clip(0, 1)
            + 0.25 * frame.note_transporteur / 5
            + 0.15 * (1 - frame.ecart_horaire_heures / 24).clip(0, 1)
            + 0.05 * (1 - frame.detour_km / 100).clip(0, 1)).to_numpy()

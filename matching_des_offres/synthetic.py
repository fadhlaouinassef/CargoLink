"""Scénarios fictifs. Les labels ne représentent pas des décisions réelles."""
import numpy as np

from .core import features, rejection_reasons


def generate(count=1200, seed=42, shipments=None, offers_per_request=30):
    rng = np.random.default_rng(seed)
    rows = []
    if shipments is not None:
        count = len(shipments)
    for i in range(count):
        weight, volume, budget = float(rng.uniform(50, 16000)), float(rng.uniform(1, 60)), float(rng.uniform(100, 1800))
        source = shipments[i] if shipments is not None else None
        request_id = source["shipment_id"] if source else f"DEM-{i:05}"
        if source:
            weight = source["weight_tons"] * 1000
        category = str(rng.choice(["palettes", "cartons", "vrac", "frais", "machines"]))
        offer_count = offers_per_request if source else int(rng.integers(4, 10))
        # Les propriétés d'une demande doivent rester constantes entre ses offres.
        request_budget = (budget if rng.random() > .1 else None) if source else budget
        strict_budget = source is not None and request_budget is not None and bool(rng.random() < .15)
        for j in range(offer_count):
            row = {
                "demande_id": request_id, "offre_id": f"OFF-{request_id}-{j}",
                "poids_kg": weight, "volume_m3": volume,
                "budget": budget if rng.random() > .1 else None,
                "budget_strict": False, "prix": float(budget * rng.uniform(.55, 1.5)),
                "capacite_kg": weight / float(rng.uniform(.25, 1.15)),
                "capacite_m3": volume / float(rng.uniform(.25, 1.15)),
                "ecart_horaire_heures": float(rng.uniform(0, 18)), "detour_km": float(rng.uniform(0, 80)),
                "note_transporteur": float(rng.uniform(2.5, 5)), "nombre_avis": int(rng.integers(0, 150)),
                "type_vehicule": str(rng.choice(["utilitaire", "camion", "frigorifique"])),
                "categorie_marchandise": category,
                **{key: bool(rng.random() > .04) for key in ["trajet_compatible", "creneau_compatible", "vehicule_disponible", "marchandise_compatible"]},
            }
            if source:
                row.update(budget=request_budget, budget_strict=strict_budget,
                           source_shipment_id=source["shipment_id"],
                           depart_ville=source["curr_loc"], arrivee_ville=source["destination"],
                           ready_time=source["ready_time"], delivery_deadline=source["delivery_deadline"],
                           source_route=source["route"], labels_simules=True)
            row["budget_strict"] = row["budget"] is not None and bool(rng.random() < .15)
            if source:
                row["budget_strict"] = strict_budget
                # Une attente simulée dépassant la fenêtre réelle rend l'offre impossible.
                row["creneau_compatible"] &= row["ecart_horaire_heures"] <= source["window_hours"]
            if row["nombre_avis"] == 0:
                row["note_transporteur"] = 0.0
            f = features(row)
            # Utilité simulée bruitée, avec interactions : aucune prétention empirique.
            utility = (3.2 * (1.05 - f["ratio_prix_budget"]) + .9 * (row["note_transporteur"] - 3.5)
                       - .08 * row["ecart_horaire_heures"] - .012 * row["detour_km"]
                       + .7 * (category == "frais" and row["type_vehicule"] == "frigorifique")
                       + .5 * (f["ratio_prix_budget"] < .9 and row["nombre_avis"] > 20)
                       + rng.normal(0, .5))
            probability = 1 / (1 + np.exp(-utility))
            row["pertinent"] = int(not rejection_reasons(row) and rng.random() < probability)
            rows.append(row)
    return rows

"""Lecture vérifiée du CSV d'expéditions ; aucune cible réelle n'est inventée."""
import csv
from datetime import datetime
import hashlib
import math


def load_shipments(path):
    columns = {"shipment_id", "route", "weight_tons", "curr_loc", "destination", "ready_time", "delivery_deadline"}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not columns.issubset(reader.fieldnames or []):
            raise ValueError(f"Colonnes CSV manquantes : {sorted(columns - set(reader.fieldnames or []))}")
        rows = list(reader)
    if not rows:
        raise ValueError("Dataset d'expéditions vide")
    seen = set()
    for row in rows:
        for key in columns:
            if not row[key] or not row[key].strip():
                raise ValueError(f"Valeur absente : {key}")
        if row["shipment_id"] in seen:
            raise ValueError(f"shipment_id dupliqué : {row['shipment_id']}")
        seen.add(row["shipment_id"])
        row["weight_tons"] = float(row["weight_tons"])
        if not math.isfinite(row["weight_tons"]) or row["weight_tons"] <= 0:
            raise ValueError("weight_tons doit être strictement positif et fini")
        row["window_hours"] = (datetime.fromisoformat(row["delivery_deadline"]) - datetime.fromisoformat(row["ready_time"])).total_seconds() / 3600
        if row["window_hours"] <= 0:
            raise ValueError("delivery_deadline doit être après ready_time")
    return rows, {"source_file": str(path.resolve()), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "source_rows": len(rows), "source_columns": sorted(columns),
                  "observed_fields": ["demande_id", "poids_kg (weight_tons * 1000)", "depart_ville", "arrivee_ville", "ready_time", "delivery_deadline", "source_route"],
                  "synthetic_fields": "Offres, volume, budget, prix, capacités, avis, catégories, compatibilités et pertinent ; le créneau tient aussi compte de la fenêtre CSV.",
                  "labels_synthetic": True}

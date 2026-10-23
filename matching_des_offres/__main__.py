"""Commandes autonomes : python -m matching_des_offres --help."""
import argparse
import hashlib
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .core import NUMERIC, CATEGORICAL, FEATURES, baseline, features, rejection_reasons
from .synthetic import generate
from .dataset import load_shipments

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
SHIPMENTS = ROOT.parent / "datasets" / "shippments_dataset.csv"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def read_rows(path, labelled=False):
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Le fichier doit contenir une liste non vide de couples demande-offre")
    seen = set()
    for row in rows:
        features(row)
        key = (row["demande_id"], row["offre_id"])
        if key in seen:
            raise ValueError(f"Couple dupliqué : {key}")
        seen.add(key)
        if labelled and (type(row.get("pertinent")) is not int or row["pertinent"] not in (0, 1)):
            raise ValueError("Chaque ligne doit avoir pertinent = 0 ou 1")
    return rows


def frame_for(rows):
    return pd.DataFrame([features(row) for row in rows], columns=FEATURES)


def metrics(rows, scores, threshold=.5):
    y = np.array([r["pertinent"] for r in rows])
    prediction = np.asarray(scores) >= threshold
    table = pd.DataFrame({"demande": [r["demande_id"] for r in rows], "y": y, "score": scores})
    top = table.sort_values("score", ascending=False, kind="stable").groupby("demande").head(3)
    return {
        "accuracy": float(accuracy_score(y, prediction)),
        "precision": float(precision_score(y, prediction, zero_division=0)),
        "recall": float(recall_score(y, prediction, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, scores)) if len(set(y)) == 2 else None,
        "precision_at_3": float(top.groupby("demande").y.mean().mean()),
        "threshold": float(threshold), "predicted_positive": int(prediction.sum()),
        "demandes_avec_candidats": int(table.demande.nunique()), "offres_admissibles": len(rows),
    }


def choose_threshold(y, scores, min_recall):
    """Maximiser la précision de validation sous une contrainte de rappel."""
    candidates = []
    for threshold in np.unique(np.r_[0.0, .5, scores]):
        predicted = scores >= threshold
        recall = recall_score(y, predicted, zero_division=0)
        if recall >= min_recall:
            precision = precision_score(y, predicted, zero_division=0)
            candidates.append((precision, f1_score(y, predicted, zero_division=0), float(threshold)))
    return max(candidates)[2]


def pipeline(classifier):
    preprocessor = ColumnTransformer([
        ("numeric", StandardScaler(), NUMERIC),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ])
    return Pipeline([("preparation", preprocessor), ("classifier", classifier)])


def train(args):
    rows = read_rows(args.data, labelled=True)
    metadata_path = args.data.with_suffix(".metadata.json")
    provenance = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {"source": "JSON fourni, provenance non vérifiée"}
    if "source_file" in provenance:
        source_rows, source_audit = load_shipments(Path(provenance["source_file"]))
        if provenance["source_sha256"] != source_audit["source_sha256"]:
            raise ValueError("Le CSV source a changé : relancer generate avant train")
        lookup = {r["shipment_id"]: r for r in source_rows}
        for row in rows:
            source = lookup.get(row.get("source_shipment_id"))
            if source is None or row["demande_id"] != source["shipment_id"]:
                raise ValueError("Identifiant d'expédition incohérent avec le CSV source")
            if row["poids_kg"] != source["weight_tons"] * 1000 or any(row[key] != source[column] for key, column in [
                ("depart_ville", "curr_loc"), ("arrivee_ville", "destination"), ("ready_time", "ready_time"), ("delivery_deadline", "delivery_deadline")]):
                raise ValueError("Données de demande incohérentes avec le CSV source")
        provenance["verified_at_training"] = True
    groups = np.array([r["demande_id"] for r in rows])
    if len(set(groups)) < 20:
        raise ValueError("Au moins 20 demandes distinctes sont nécessaires")
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=args.seed).split(rows, groups=groups))
    train_local, val_local = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=args.seed).split(trainval, groups=groups[trainval]))
    splits = {"train": trainval[train_local], "validation": trainval[val_local], "test": test}
    sets = {k: set(groups[index]) for k, index in splits.items()}
    assert not (sets["train"] & sets["validation"] or sets["train"] & sets["test"] or sets["validation"] & sets["test"])
    subsets = {name: [rows[int(i)] for i in indices if not rejection_reasons(rows[int(i)])] for name, indices in splits.items()}
    for name, subset in subsets.items():
        if len({r["pertinent"] for r in subset}) != 2:
            raise ValueError(f"{name} doit contenir les deux classes parmi les offres admissibles")
    x_train = frame_for(subsets["train"])
    y_train = [r["pertinent"] for r in subsets["train"]]
    candidates = {
        "logistic_regression": pipeline(LogisticRegression(max_iter=1500, random_state=args.seed)),
        "random_forest": pipeline(RandomForestClassifier(n_estimators=180, min_samples_leaf=6, n_jobs=-1, random_state=args.seed)),
    }
    for c in [.1, 10]:
        candidates[f"logistic_C_{c}"] = pipeline(LogisticRegression(C=c, max_iter=1500, random_state=args.seed))
    for leaf in [12, 24]:
        candidates[f"random_forest_leaf_{leaf}"] = pipeline(RandomForestClassifier(n_estimators=250, min_samples_leaf=leaf, n_jobs=-1, random_state=args.seed))
    for leaves in [7, 15]:
        candidates[f"hist_gradient_boosting_{leaves}"] = pipeline(HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=leaves, l2_regularization=5, random_state=args.seed))
    validation = {"baseline": metrics(subsets["validation"], baseline(frame_for(subsets["validation"])))}
    thresholds = {}
    for name, model in candidates.items():
        model.fit(x_train, y_train)
        scores = model.predict_proba(frame_for(subsets["validation"]))[:, 1]
        thresholds[name] = choose_threshold([r["pertinent"] for r in subsets["validation"]], scores, args.min_recall)
        validation[name] = metrics(subsets["validation"], scores, thresholds[name])
    selected = max(candidates, key=lambda name: (validation[name]["precision"], validation[name]["precision_at_3"], validation[name]["f1"]))
    # Le test reste réservé au modèle choisi via la validation et à la référence.
    model = candidates[selected]
    test_scores = model.predict_proba(frame_for(subsets["test"]))[:, 1]
    test_metrics = metrics(subsets["test"], test_scores, thresholds[selected])
    old_selected = max(["logistic_regression", "random_forest"], key=lambda name: (
        validation[name]["precision_at_3"], metrics(subsets["validation"], candidates[name].predict_proba(frame_for(subsets["validation"]))[:, 1])["f1"]))
    previous_method_test = metrics(subsets["test"], candidates[old_selected].predict_proba(frame_for(subsets["test"]))[:, 1])
    baseline_test = metrics(subsets["test"], baseline(frame_for(subsets["test"])))
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "selected_model": selected, "seed": args.seed,
        "selection_objective": "Précision maximale sur validation, rappel >= min_validation_recall ; départage Precision@3 puis F1",
        "min_validation_recall": args.min_recall, "threshold": thresholds[selected],
        "test_at_threshold_0_5": metrics(subsets["test"], test_scores),
        "previous_method_model": old_selected, "previous_method_test": previous_method_test,
        "delta_precision_previous_method": test_metrics["precision"] - previous_method_test["precision"],
        "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "provenance": "Détails dans data_provenance ; le CSV d'expéditions ne fournit pas de labels de pertinence.",
        "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__, "joblib": joblib.__version__},
        "features": FEATURES, "validation": validation, "test": test_metrics, "baseline_test": baseline_test,
        "delta_precision_at_3": test_metrics["precision_at_3"] - baseline_test["precision_at_3"],
        "split": {name: {"demandes": len(sets[name]), "offres_total": len(splits[name]), "offres_admissibles": len(subsets[name])} for name in splits},
        "group_overlap": 0,
    }
    report["data_provenance"] = provenance
    joblib.dump({"pipeline": model, "metadata": report, "train_validation_ids": sorted(sets["train"] | sets["validation"])}, args.output / "model.joblib")
    write_json(args.output / "rapport.json", report)
    write_json(args.output / "split_ids.json", {name: sorted(ids) for name, ids in sets.items()})
    write_json(args.output / "test.json", [rows[int(i)] for i in test])
    print(json.dumps(report, ensure_ascii=False, indent=2))


def rank(rows, model, threshold=.5):
    accepted, rejected = [], []
    for row in rows:
        reasons = rejection_reasons(row)
        if reasons:
            rejected.append({"demande_id": row["demande_id"], "offre_id": row["offre_id"], "motifs": reasons})
        else:
            accepted.append(row)
    ranked = []
    if accepted:
        scores = model.predict_proba(frame_for(accepted))[:, 1]
        for row, score in zip(accepted, scores):
            ranked.append({"demande_id": row["demande_id"], "offre_id": row["offre_id"], "score": round(float(score) * 100, 2),
                           "pertinent_predit": bool(score >= threshold),
                           "prix_tnd": row["prix"], "depasse_budget": row["budget"] is not None and row["prix"] > row["budget"],
                           "criteres_verifies": ["Trajet et créneau compatibles", "Capacités suffisantes", "Véhicule disponible", "Marchandise compatible"]})
    ranked.sort(key=lambda r: (r["demande_id"], -r["score"], r["offre_id"]))
    counters = {}
    for row in ranked:
        counters[row["demande_id"]] = counters.get(row["demande_id"], 0) + 1
        row["rang"] = counters[row["demande_id"]]
    return {"classement": ranked, "offres_exclues": rejected}


def evaluate(args):
    bundle = joblib.load(args.model)
    rows = read_rows(args.data, labelled=True)
    if set(r["demande_id"] for r in rows) & set(bundle["train_validation_ids"]):
        raise ValueError("Évaluation refusée : demandes déjà utilisées en entraînement/validation")
    result = rank(rows, bundle["pipeline"])
    admitted = [r for r in rows if not rejection_reasons(r)]
    lookup = {(r["demande_id"], r["offre_id"]): r for r in rows}
    report = {"offres_total": len(rows), "offres_exclues": len(result["offres_exclues"]),
              "violations_contraintes": sum(bool(rejection_reasons(lookup[r["demande_id"], r["offre_id"]])) for r in result["classement"])}
    report["model"] = metrics(admitted, bundle["pipeline"].predict_proba(frame_for(admitted))[:, 1], bundle["metadata"].get("threshold", .5)) if admitted else None
    report["baseline"] = metrics(admitted, baseline(frame_for(admitted))) if admitted else None
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Matching des offres autonome, sans Django")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Créer des données SYNTHÉTIQUES")
    gen.add_argument("--requests", type=int, default=1200)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--source", type=Path, default=SHIPMENTS)
    gen.add_argument("--offers-per-request", type=int, default=30)
    gen.add_argument("--synthetic-only", action="store_true", help="Ancienne simulation entièrement fictive, sans CSV")
    gen.add_argument("--output", type=Path, default=DATA / "matching_dataset.json")
    tr = sub.add_parser("train")
    tr.add_argument("--data", type=Path, default=DATA / "matching_dataset.json")
    tr.add_argument("--output", type=Path, default=ARTIFACTS)
    tr.add_argument("--seed", type=int, default=42)
    tr.add_argument("--min-recall", type=float, default=.5, help="Rappel minimal sur validation pour choisir le seuil")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--data", type=Path, default=ARTIFACTS / "test.json")
    ev.add_argument("--model", type=Path, default=ARTIFACTS / "model.joblib")
    pr = sub.add_parser("predict")
    pr.add_argument("--input", type=Path, default=ROOT / "exemple.json")
    pr.add_argument("--model", type=Path, default=ARTIFACTS / "model.joblib")
    args = parser.parse_args()
    try:
        if args.command == "generate":
            if args.requests < 20:
                raise ValueError("--requests doit être au moins 20")
            if args.offers_per_request < 4:
                raise ValueError("--offers-per-request doit être au moins 4")
            if args.synthetic_only:
                rows = generate(args.requests, args.seed)
                provenance = {"synthetic": True, "labels_synthetic": True}
            else:
                shipments, provenance = load_shipments(args.source)
                rows = generate(seed=args.seed, shipments=shipments, offers_per_request=args.offers_per_request)
            write_json(args.output, rows)
            provenance.update(seed=args.seed, requests=len({r["demande_id"] for r in rows}), rows=len(rows), labels="Utilité simulée bruitée, sans décisions utilisateur réelles")
            write_json(args.output.with_suffix(".metadata.json"), provenance)
            print(json.dumps(provenance, ensure_ascii=False, indent=2))
            print(f"Fichier préparé : {args.output}")
        elif args.command == "train":
            if not 0 < args.min_recall <= 1:
                raise ValueError("--min-recall doit être dans ]0, 1]")
            train(args)
        elif args.command == "evaluate":
            evaluate(args)
        else:
            bundle = joblib.load(args.model)
            result = rank(read_rows(args.input), bundle["pipeline"], bundle["metadata"].get("threshold", .5))
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"Erreur : {exc}\n")


if __name__ == "__main__":
    main()

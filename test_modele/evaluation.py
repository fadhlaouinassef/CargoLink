"""python -m test_modele.evaluation : rapports et captures du modèle existant."""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, classification_report, confusion_matrix,
    precision_recall_curve, roc_curve,
)

from matching_des_offres.__main__ import (
    ARTIFACTS, DATA, SHIPMENTS, baseline, frame_for, metrics, read_rows, write_json,
)
from matching_des_offres.core import NUMERIC, rejection_reasons
from . import visuels as v

ROOT = Path(__file__).resolve().parent
LIMITATION = "Labels de pertinence simulés : ces résultats ne mesurent pas la précision réelle en production."


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_splits(rows, test_rows, splits, bundle):
    """Refuser toute fuite ou incohérence avant de calculer les métriques."""
    sets = {name: set(splits[name]) for name in ("train", "validation", "test")}
    if any(sets[a] & sets[b] for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))):
        raise ValueError("Fuite de données : recouvrement des demandes entre ensembles")
    if sets["train"] | sets["validation"] != set(bundle["train_validation_ids"]):
        raise ValueError("Les splits ne correspondent pas au modèle sauvegardé")
    if set(r["demande_id"] for r in rows) != set.union(*sets.values()):
        raise ValueError("Les groupes du dataset ne correspondent pas aux splits")
    expected = {(r["demande_id"], r["offre_id"]): r for r in rows if r["demande_id"] in sets["test"]}
    actual = {(r["demande_id"], r["offre_id"]): r for r in test_rows}
    if actual != expected:
        raise ValueError("Le test réservé diffère du dataset ou de ses groupes de test")
    return {name: [r for r in rows if r["demande_id"] in ids] for name, ids in sets.items()}


def summarize(rows, scores, threshold):
    if not rows:
        raise ValueError("Aucune offre admissible à évaluer")
    y = np.array([r["pertinent"] for r in rows])
    scores = np.asarray(scores, dtype=float)
    if scores.shape != y.shape or not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise ValueError("Scores invalides : une probabilité finie par offre est requise")
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Seuil invalide")
    predicted = (scores >= threshold).astype(int)
    cm = confusion_matrix(y, predicted, labels=[0, 1])
    normalized = np.divide(cm, cm.sum(axis=1, keepdims=True), out=np.zeros((2, 2), dtype=float), where=cm.sum(axis=1, keepdims=True) != 0)
    result = metrics(rows, scores, threshold)
    result.update(
        average_precision=float(average_precision_score(y, scores)) if len(set(y)) == 2 else None,
        confusion_matrix=cm.tolist(), confusion_matrix_normalized=normalized.tolist(),
        confusion_axes="lignes = labels réels [0, 1], colonnes = prédictions [0, 1]",
        classification_report=classification_report(y, predicted, labels=[0, 1], target_names=["non_pertinent", "pertinent"], output_dict=True, zero_division=0),
    )
    return result


def run(args):
    # Ce joblib est l'artefact local du projet ; aucun téléchargement de modèle.
    bundle = joblib.load(args.artifacts / "model.joblib")
    metadata = bundle["metadata"]
    if sha256(args.data) != metadata["data_sha256"]:
        raise ValueError("Le dataset ne correspond pas à l'empreinte enregistrée pendant l'entraînement")
    rows = read_rows(args.data, labelled=True)
    test_rows = read_rows(args.artifacts / "test.json", labelled=True)
    splits = json.loads((args.artifacts / "split_ids.json").read_text(encoding="utf-8"))
    subsets = verify_splits(rows, test_rows, splits, bundle)
    admitted = {name: [r for r in subset if not rejection_reasons(r)] for name, subset in subsets.items()}
    if any(not subset for subset in admitted.values()):
        raise ValueError("Chaque ensemble doit contenir des offres admissibles")
    model, threshold = bundle["pipeline"], float(metadata.get("threshold", .5))
    scores = {name: model.predict_proba(frame_for(subset))[:, 1] for name, subset in admitted.items()}
    summaries = {name: summarize(subset, scores[name], threshold) for name, subset in admitted.items()}
    reference = summarize(admitted["test"], baseline(frame_for(admitted["test"])), .5)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "limitation": LIMITATION,
        "scope": "Classification sur offres admissibles après filtrage métier ; train est une mesure de réajustement, test est réservé.",
        "selected_model": metadata["selected_model"], "threshold": threshold,
        "model_file": str((args.artifacts / "model.joblib").resolve()),
        "model_sha256": sha256(args.artifacts / "model.joblib"), "data_sha256": sha256(args.data),
        "training_versions": metadata.get("versions"), "data_provenance": metadata.get("data_provenance"),
        "group_overlap": 0,
        "split": {name: {"demandes": len(splits[name]), "total": len(subsets[name]), "admissibles": len(admitted[name]), "exclues": len(subsets[name]) - len(admitted[name])} for name in subsets},
        "scores": summaries, "baseline_test": reference,
        "validation_candidates_at_training": metadata["validation"],
    }
    output = args.output
    captures, exports = output / "captures", output / "exports"
    captures.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)
    write_json(output / "rapport_evaluation.json", report)
    write_json(output / "rapport_entrainement_original.json", metadata)
    for name, summary in summaries.items():
        pd.DataFrame(summary["classification_report"]).to_csv(exports / f"classification_{name}.csv", encoding="utf-8-sig")
        pd.DataFrame(summary["confusion_matrix"], index=["reel_0", "reel_1"], columns=["predit_0", "predit_1"]).to_csv(exports / f"confusion_{name}.csv", encoding="utf-8-sig")
    predictions = []
    for name, subset in subsets.items():
        lookup = {(r["demande_id"], r["offre_id"]): float(score) for r, score in zip(admitted[name], scores[name])}
        for row in subset:
            score = lookup.get((row["demande_id"], row["offre_id"]))
            predictions.append({"ensemble": name, "demande_id": row["demande_id"], "offre_id": row["offre_id"], "pertinent_reel": row["pertinent"], "score": score, "pertinent_predit": int(score >= threshold) if score is not None else None, "motifs_exclusion": " ; ".join(rejection_reasons(row))})
    pd.DataFrame(predictions).to_csv(exports / "predictions.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(rows).head(15).to_csv(exports / "apercu_dataset.csv", index=False, encoding="utf-8-sig")
    keys = ["accuracy", "precision", "recall", "f1", "roc_auc", "precision_at_3"]
    pd.DataFrame({name: {key: value[key] for key in keys} for name, value in summaries.items()}).to_csv(exports / "metriques.csv", encoding="utf-8-sig")
    labels = ["Non pertinent (0)", "Pertinent (1)"]
    test = summaries["test"]
    for name, summary in summaries.items():
        v.heatmap(captures / f"confusion_{name}.png", f"Matrice de confusion : {name}", f"Lignes : réel | Colonnes : prédit | Offres admissibles | Seuil = {threshold:.6f}", summary["confusion_matrix"], labels)
    v.heatmap(captures / "confusion_test_normalisee.png", "Matrice de confusion normalisée : test", "Normalisation par ligne réelle | 0 = non pertinent, 1 = pertinent", test["confusion_matrix_normalized"], labels, normalized=True)
    v.bars(captures / "precision_test.png", "Performance sur le test réservé", f"{metadata['selected_model']} | Seuil issu de validation = {threshold:.6f}", ["Accuracy", "Précision", "Rappel", "F1", "AUC ROC", "Précision@3"], [("Modèle IA", [test[k] or 0 for k in keys], v.BLUE), ("Référence fixe (seuil 0,5)", [reference[k] or 0 for k in keys], v.ORANGE)], maximum=1)
    v.bars(captures / "train_validation_test.png", "Entraînement, validation et test", "Même modèle sauvegardé, même seuil | Train : mesure sur données d'apprentissage", ["Accuracy", "Précision", "Rappel", "F1"], [(name, [summaries[name][k] for k in keys[:4]], color) for name, color in zip(summaries, [v.BLUE, v.ORANGE, v.GREEN])], maximum=1)
    v.bars(captures / "repartition_dataset.png", "Répartition des données", "Séparation par demande | Aucun recouvrement de groupes", list(subsets), [("Demandes", [len(splits[n]) for n in subsets], v.BLUE), ("Offres admissibles", [len(admitted[n]) for n in subsets], v.GREEN), ("Offres exclues", [report["split"][n]["exclues"] for n in subsets], v.ORANGE)])
    v.bars(captures / "classes_dataset.png", "Distribution des classes admissibles", "Les labels sont simulés | Les offres exclues ne participent pas aux scores IA", list(subsets), [(label, [sum(r["pertinent"] == i for r in admitted[n]) for n in subsets], color) for i, (label, color) in enumerate(zip(labels, [v.BLUE, v.ORANGE]))])
    fields = ["demande_id", "offre_id", "poids_kg", "prix", "budget", "pertinent"]
    preview = [[str(row[k]) if not isinstance(row[k], float) else f"{row[k]:.2f}" for k in fields] for row in rows[:10]]
    v.table(captures / "apercu_dataset.png", "Aperçu du dataset de matching", f"{len(rows)} couples demande-offre | Premières lignes | Prix en TND, poids en kg", fields, preview)
    source = metadata.get("data_provenance", {}).get("source_file")
    if source:
        # Préférer le chemin local portable, puis celui conservé dans la provenance.
        source_path = args.source or (SHIPMENTS if SHIPMENTS.exists() else Path(source))
        expected_hash = metadata["data_provenance"].get("source_sha256")
        if expected_hash and sha256(source_path) != expected_hash:
            raise ValueError("Le CSV source a changé depuis l'entraînement")
        source_frame = pd.read_csv(source_path)
        source_frame.head(10).to_csv(exports / "apercu_source.csv", index=False, encoding="utf-8-sig")
        columns = ["shipment_id", "weight_tons", "curr_loc", "destination", "ready_time"]
        v.table(captures / "apercu_source_csv.png", "Aperçu du CSV source", f"{len(source_frame)} expéditions | Ce CSV ne contient pas de cible pertinent", columns, source_frame[columns].head(10).astype(str).values.tolist())
    candidates = [[name, f"{value['precision']:.4f}", f"{value['recall']:.4f}", f"{value['f1']:.4f}", f"{value['threshold']:.6f}"] for name, value in metadata["validation"].items()]
    v.table(captures / "comparaison_entrainement.png", "Comparaison des candidats à l'entraînement", f"Scores de validation enregistrés | Modèle retenu : {metadata['selected_model']}", ["Candidat", "Précision", "Rappel", "F1", "Seuil"], candidates)
    # Matrice de corrélation descriptive sur train uniquement, sans les identifiants.
    frame = frame_for(admitted["train"])[NUMERIC].copy()
    frame["pertinent"] = [r["pertinent"] for r in admitted["train"]]
    corr = frame.corr()
    corr.to_csv(exports / "correlations_train.csv", encoding="utf-8-sig")
    short = ["Prix/budget", "Budget absent", "Écart horaire", "Détour", "Poids/cap.", "Volume/cap.", "Note", "Nb avis", "Pertinent"]
    v.heatmap(captures / "correlations_train.png", "Corrélations de Pearson : entraînement", "Colonnes numérotées comme les lignes | Bleu = intensité absolue | Tiret : constante", corr.to_numpy(), short, normalized=True)
    y = np.array([r["pertinent"] for r in admitted["test"]])
    if len(set(y)) == 2:
        roc, pr = [], []
        for name, score, color in [("Modèle IA", scores["test"], v.BLUE), ("Référence fixe", baseline(frame_for(admitted["test"])), v.ORANGE)]:
            fpr, tpr, _ = roc_curve(y, score)
            precision, recall, _ = precision_recall_curve(y, score)
            roc.append((name, fpr, tpr, color))
            # Courbe PR en escalier : chaque intervalle conserve la précision de son extrémité.
            pr.append((name, np.repeat(recall, 2)[1:], np.repeat(precision, 2)[:-1], color))
        v.lines(captures / "courbe_roc_test.png", "Courbe ROC : test réservé", f"AUC du modèle = {test['roc_auc']:.4f} | Diagonale : classement aléatoire", roc, "Taux de faux positifs", "Taux de vrais positifs", diagonal=True)
        v.lines(captures / "courbe_precision_rappel_test.png", "Courbe précision-rappel : test réservé", f"Average precision = {test['average_precision']:.4f} | Proportion positive = {y.mean():.4f}", pr, "Rappel", "Précision")
    image_names = sorted(p.name for p in captures.glob("*.png"))
    html = '<!doctype html><html lang="fr"><meta charset="utf-8"><title>Évaluation CargoLink</title><style>body{font:18px Arial;margin:40px auto;max-width:1200px;color:#0f172a}img{width:100%;border:1px solid #cbd5e1}section{margin:35px 0}p{line-height:1.6}</style>'
    html += f"<h1>Évaluation du modèle de matching</h1><p>{escape(LIMITATION)}</p><p>Modèle : {escape(metadata['selected_model'])} ; seuil : {threshold:.6f}. Matrices : lignes réelles, colonnes prédites. Scores IA calculés sur offres admissibles uniquement. Les offres exclues sont listées dans exports/predictions.csv.</p>"
    html += "<p>Le graphique train/validation/test compare des scores du modèle déjà entraîné. Ce n'est pas une courbe d'apprentissage par époque ; cet historique n'est pas enregistré par l'entraînement existant. Le modèle et le seuil ont été sélectionnés sur validation : ses scores participent donc à la sélection.</p>"
    html += "".join(f'<section><h2>{escape(name)}</h2><img src="captures/{escape(name)}" alt="{escape(name)}"></section>' for name in image_names)
    (output / "rapport.html").write_text(html + "</html>", encoding="utf-8")
    print(json.dumps({"rapport": str((output / "rapport.html").resolve()), "captures": len(image_names), "test": {k: test[k] for k in keys}, "confusion_test": test["confusion_matrix"], "limitation": LIMITATION}, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA / "matching_dataset.json")
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    parser.add_argument("--output", type=Path, default=ROOT / "resultats")
    parser.add_argument("--source", type=Path, help="CSV source local, avec la même empreinte qu'à l'entraînement")
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"Erreur : {exc}\n")


if __name__ == "__main__":
    main()

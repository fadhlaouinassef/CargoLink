"""Tests des calculs et de l'isolation des ensembles d'évaluation."""
from copy import deepcopy
import json
import unittest

import joblib
import numpy as np

from matching_des_offres.__main__ import ARTIFACTS, DATA, frame_for, read_rows
from matching_des_offres.core import rejection_reasons
from .evaluation import summarize, verify_splits


class EvaluationTests(unittest.TestCase):
    def test_known_confusion_and_metrics_at_saved_threshold(self):
        rows = [{"demande_id": f"d{i}", "pertinent": y} for i, y in enumerate([0, 0, 1, 1])]
        result = summarize(rows, [.1, .7, .6, .9], .65)
        self.assertEqual(result["confusion_matrix"], [[1, 1], [1, 1]])
        for name in ["accuracy", "precision", "recall", "f1"]:
            self.assertEqual(result[name], .5)

    def test_single_class_retains_two_by_two_matrix(self):
        result = summarize([{"demande_id": "d", "pertinent": 0}], [.1], .5)
        self.assertEqual(result["confusion_matrix"], [[1, 0], [0, 0]])
        self.assertIsNone(result["roc_auc"])
        self.assertIsNone(result["average_precision"])
        self.assertTrue(np.isfinite(result["confusion_matrix_normalized"]).all())

    def test_empty_or_invalid_scores_fail(self):
        with self.assertRaisesRegex(ValueError, "Aucune"):
            summarize([], [], .5)
        rows = [{"demande_id": "d", "pertinent": 1}]
        for scores in [[float("nan")], [1.1], [], [[.2]]]:
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                summarize(rows, scores, .5)

    def test_leakage_or_modified_holdout_rejected(self):
        rows = [{"demande_id": name, "offre_id": "o", "pertinent": 0} for name in ["a", "b", "c"]]
        splits = {"train": ["a"], "validation": ["b"], "test": ["c"]}
        bundle = {"train_validation_ids": ["a", "b"]}
        self.assertEqual(len(verify_splits(rows, rows[2:], splits, bundle)["test"]), 1)
        bad = deepcopy(splits)
        bad["test"].append("a")
        with self.assertRaisesRegex(ValueError, "Fuite"):
            verify_splits(rows, rows[2:], bad, bundle)
        with self.assertRaisesRegex(ValueError, "diffère"):
            verify_splits(rows, [rows[2] | {"pertinent": 1}], splits, bundle)

    def test_saved_model_reproduces_training_report_on_reserved_test(self):
        if not (ARTIFACTS / "model.joblib").exists():
            self.skipTest("Modèle absent : lancer train")
        bundle = joblib.load(ARTIFACTS / "model.joblib")
        rows = read_rows(DATA / "matching_dataset.json", labelled=True)
        holdout = read_rows(ARTIFACTS / "test.json", labelled=True)
        splits = json.loads((ARTIFACTS / "split_ids.json").read_text(encoding="utf-8"))
        verify_splits(rows, holdout, splits, bundle)
        admitted = [r for r in holdout if not rejection_reasons(r)]
        scores = bundle["pipeline"].predict_proba(frame_for(admitted))[:, 1]
        result = summarize(admitted, scores, bundle["metadata"]["threshold"])
        for key in ["accuracy", "precision", "recall", "f1", "roc_auc", "precision_at_3"]:
            self.assertAlmostEqual(result[key], bundle["metadata"]["test"][key], places=12)
        self.assertEqual(np.asarray(result["confusion_matrix"]).sum(), len(admitted))


if __name__ == "__main__":
    unittest.main()

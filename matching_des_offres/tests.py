"""Tests autonomes, sans accès à Django ni à sa base."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import joblib
import numpy as np

from .core import features, rejection_reasons
from .synthetic import generate
from .__main__ import ARTIFACTS, ROOT, SHIPMENTS, choose_threshold, evaluate, frame_for, metrics, rank, read_rows, train, write_json
from .dataset import load_shipments


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.row = json.loads((ROOT / "exemple.json").read_text(encoding="utf-8"))[0]

    def test_example_rejects_b(self):
        rows = read_rows(ROOT / "exemple.json")
        self.assertEqual([bool(rejection_reasons(r)) for r in rows], [False, True, False])

    def test_every_hard_constraint(self):
        for key, value in [("capacite_kg", 100), ("capacite_m3", 1),
                           ("trajet_compatible", False), ("creneau_compatible", False),
                           ("vehicule_disponible", False), ("marchandise_compatible", False)]:
            with self.subTest(key=key):
                row = self.row | {key: value}
                self.assertTrue(rejection_reasons(row))

    def test_budget_optional_or_strict(self):
        row = self.row | {"budget": None}
        self.assertEqual(features(row)["budget_absent"], 1)
        self.assertEqual(rejection_reasons(row), [])
        row = self.row | {"prix": 200}
        self.assertEqual(rejection_reasons(row), [])
        self.assertTrue(rejection_reasons(row | {"budget_strict": True}))

    def test_bad_inputs_fail(self):
        for change in [{"capacite_kg": 0}, {"prix": -1}, {"volume_m3": float("nan")},
                       {"budget": float("inf")}, {"vehicule_disponible": "false"},
                       {"budget_strict": True, "budget": None}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                rejection_reasons(self.row | change)

    def test_capacity_boundary_and_new_carrier(self):
        row = self.row | {"capacite_kg": 350, "capacite_m3": 2.4, "note_transporteur": 0, "nombre_avis": 0}
        self.assertEqual(rejection_reasons(row), [])
        self.assertEqual(features(row)["ratio_poids"], 1)

    def test_generator_reproducible(self):
        self.assertEqual(generate(20, 10), generate(20, 10))

    def test_precision_at_three_macro(self):
        rows = [{"demande_id": "a", "pertinent": 1}, {"demande_id": "b", "pertinent": 0},
                {"demande_id": "b", "pertinent": 0}, {"demande_id": "b", "pertinent": 1}]
        self.assertAlmostEqual(metrics(rows, [.9, .8, .7, .6])["precision_at_3"], 2 / 3)

    def test_duplicate_pair_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pairs.json"
            path.write_text(json.dumps([self.row, self.row]), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_rows(path)


class TrainedModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ARTIFACTS / "model.joblib").exists():
            raise unittest.SkipTest("Lancer train pour tester le modèle sauvegardé")
        cls.bundle = joblib.load(ARTIFACTS / "model.joblib")
        cls.rows = read_rows(ROOT / "exemple.json")

    def test_prediction_and_persistence(self):
        model = self.bundle["pipeline"]
        before = model.predict_proba(frame_for(self.rows))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.joblib"
            joblib.dump(model, path)
            np.testing.assert_allclose(before, joblib.load(path).predict_proba(frame_for(self.rows)))
        result = rank(self.rows, model)
        self.assertEqual({r["offre_id"] for r in result["classement"]}, {"A", "C"})
        self.assertEqual(result["offres_exclues"][0]["offre_id"], "B")
        self.assertEqual([r["rang"] for r in result["classement"]], [1, 2])

    def test_all_rejected_and_unknown_category(self):
        self.assertEqual(rank([self.rows[1]], self.bundle["pipeline"])["classement"], [])
        row = deepcopy(self.rows[0])
        row["type_vehicule"] = "nouveau_type"
        self.assertEqual(len(rank([row], self.bundle["pipeline"])["classement"]), 1)

    def test_no_overlap(self):
        split = json.loads((ARTIFACTS / "split_ids.json").read_text(encoding="utf-8"))
        self.assertFalse(set(split["train"]) & set(split["validation"]))
        self.assertFalse(set(split["test"]) & (set(split["train"]) | set(split["validation"])))

    def test_evaluation_refuses_training_requests(self):
        row = self.rows[0] | {"demande_id": self.bundle["train_validation_ids"][0], "pertinent": 1}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "leak.json"
            path.write_text(json.dumps([row]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "déjà utilisées"):
                evaluate(SimpleNamespace(model=ARTIFACTS / "model.joblib", data=path))

    def test_no_impossible_offer_in_full_holdout_ranking(self):
        rows = read_rows(ARTIFACTS / "test.json", labelled=True)
        result = rank(rows, self.bundle["pipeline"])
        lookup = {(r["demande_id"], r["offre_id"]): r for r in rows}
        for r in result["classement"]:
            self.assertFalse(rejection_reasons(lookup[r["demande_id"], r["offre_id"]]))
        self.assertEqual(len(rows), len(result["classement"]) + len(result["offres_exclues"]))


class DatasetAndThresholdTests(unittest.TestCase):
    def test_source_values_used_in_generated_requests(self):
        sources, audit = load_shipments(SHIPMENTS)
        rows = generate(seed=42, shipments=sources, offers_per_request=4)
        self.assertEqual(len(rows), len(sources) * 4)
        self.assertTrue(audit["labels_synthetic"])
        lookup = {r["shipment_id"]: r for r in sources}
        for row in rows:
            source = lookup[row["demande_id"]]
            self.assertEqual(row["poids_kg"], source["weight_tons"] * 1000)
            self.assertEqual(row["depart_ville"], source["curr_loc"])
            self.assertEqual(row["arrivee_ville"], source["destination"])
            self.assertEqual(row["ready_time"], source["ready_time"])
            self.assertEqual(row["delivery_deadline"], source["delivery_deadline"])

    def test_source_mismatch_blocks_training(self):
        sources, audit = load_shipments(SHIPMENTS)
        rows = generate(seed=42, shipments=sources, offers_per_request=4)
        rows[0]["poids_kg"] += 1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.json"
            write_json(path, rows)
            write_json(path.with_suffix(".metadata.json"), audit)
            with self.assertRaisesRegex(ValueError, "incohérentes"):
                train(SimpleNamespace(data=path))

    def test_missing_source_is_not_silently_replaced(self):
        with self.assertRaises(FileNotFoundError):
            load_shipments(ROOT / "source_absente.csv")

    def test_threshold_optimizes_precision_with_recall_floor(self):
        y = np.array([0, 0, 1, 1, 1, 0])
        scores = np.array([.1, .2, .4, .6, .9, .55])
        threshold = choose_threshold(y, scores, .5)
        predicted = scores >= threshold
        self.assertGreaterEqual(float(predicted[y == 1].mean()), .5)
        self.assertAlmostEqual(threshold, .6)

    def test_threshold_changes_classification_not_ranking_metric(self):
        rows = [{"demande_id": "a", "pertinent": 1}, {"demande_id": "a", "pertinent": 0}]
        low, high = metrics(rows, [.8, .6], .5), metrics(rows, [.8, .6], .7)
        self.assertEqual(low["precision_at_3"], high["precision_at_3"])
        self.assertGreater(high["precision"], low["precision"])


if __name__ == "__main__":
    unittest.main()

"""Tests unitaires de la logique de comparaison d'évaluation sans réseau."""
from django.test import SimpleTestCase

from vehicules.ia.evaluation import (
    compare_date,
    compare_type_vehicule,
    compare_zone,
    evaluate_phrase_result,
    normalize_zone,
)


class EvaluationLogicTests(SimpleTestCase):
    def test_normalize_zone(self):
        self.assertEqual(normalize_zone("Sousse"), "sousse")
        self.assertEqual(normalize_zone("  Béja  "), "beja")
        self.assertEqual(normalize_zone("Médenine"), "medenine")
        self.assertIsNone(normalize_zone(""))
        self.assertIsNone(normalize_zone(None))

    def test_compare_zone(self):
        self.assertTrue(compare_zone("Béja", "beja"))
        self.assertTrue(compare_zone("Tunis", "TUNIS"))
        self.assertTrue(compare_zone(None, None))
        self.assertFalse(compare_zone("Tunis", "Sfax"))
        self.assertFalse(compare_zone("Tunis", None))
        self.assertFalse(compare_zone(None, "Tunis"))

    def test_compare_date(self):
        self.assertTrue(compare_date("2026-11-05T08:00", "2026-11-05T08:00"))
        self.assertTrue(compare_date(None, None))
        self.assertFalse(compare_date("2026-11-05T08:00", "2026-11-05T18:00"))
        self.assertFalse(compare_date("2026-11-05T08:00", None))

    def test_compare_type_vehicule(self):
        self.assertTrue(compare_type_vehicule("camion", "CAMION"))
        self.assertTrue(compare_type_vehicule("semi_remorque", "semi_remorque"))
        self.assertTrue(compare_type_vehicule(None, None))
        self.assertFalse(compare_type_vehicule("camion", "plateau"))

    def test_evaluate_phrase_result_exact(self):
        attendu = {
            "zone_depart": "Tunis",
            "zone_arrivee": "Sfax",
            "date_debut": "2026-11-05T08:00",
            "date_fin": "2026-11-08T18:00",
            "type_vehicule": "camion",
        }
        obtenu = {
            "zone_depart": "tunis",
            "zone_arrivee": "SFAX",
            "date_debut": "2026-11-05T08:00",
            "date_fin": "2026-11-08T18:00",
            "type_vehicule": "camion",
        }
        res = evaluate_phrase_result(attendu, obtenu)
        self.assertTrue(res["global_match"])
        self.assertFalse(res["has_hallucination"])

    def test_evaluate_phrase_result_hallucination_detection(self):
        attendu = {
            "zone_depart": None,
            "zone_arrivee": "Sousse",
            "date_debut": None,
            "date_fin": None,
            "type_vehicule": None,
        }
        obtenu = {
            "zone_depart": "Tunis",  # Hallucination !
            "zone_arrivee": "Sousse",
            "date_debut": None,
            "date_fin": None,
            "type_vehicule": "camion",  # Hallucination !
        }
        res = evaluate_phrase_result(attendu, obtenu)
        self.assertFalse(res["global_match"])
        self.assertTrue(res["has_hallucination"])
        self.assertIn("zone_depart", res["hallucination_fields"])
        self.assertIn("type_vehicule", res["hallucination_fields"])

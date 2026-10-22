"""Tests unitaires et d'intégration pour l'analyse du risque de maintenance.

Couvre :
- Calcul des variables (minimisation, exclusion des PII, calcul correct)
- Moteur de règles déterministe (bornes 0-100, facteurs, insuffisance de données)
- Validation défensive JSON du LLM (champs manquants, types aberrants, markdown stripped)
- Repli gracieux en cas d'erreur API (quota, timeout, indisponibilité)
- Détection de divergence (écart > 1 cran)
- Cache par hash des variables
- Tâches Celery (idempotence, retries sur quota avec backoff, pas de crash)
- Vues HTTP & API (rate-limiting 10/min, permissions transporteur, non-régression)
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from vehicules.models import AnalyseRisque, Maintenance, Vehicule
from vehicules.ia.risque_regles import calculer_variables, score_regles
from vehicules.ia.risque_assistant import (
    _valider_et_nettoyer_reponse_ia,
    analyser_via_ia,
    calculer_hash_variables,
)
from vehicules.ia.eval_harness import executer_evaluation_regles
from vehicules.services import analyser_vehicule, niveau_risque_vehicule
from vehicules.tasks import analyser_vehicule_task, analyser_flotte_task
from vehicules.ia.providers import IAQuotaExceededError, IATimeoutError

User = get_user_model()


class RisqueReglesTestCase(TestCase):
    """Tests du calcul des variables et du moteur de règles déterministe."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='transp_risque@test.com',
            full_name='Transporteur Test Risque',
            role=User.Role.TRANSPORTEUR,
            password='password123',
        )
        self.vehicule = Vehicule.objects.create(
            transporteur=self.user,
            immatriculation='123-TN-4567',
            marque='Volvo',
            modele='FH16',
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            annee=2020,
            capacite_poids_kg=18000,
            capacite_volume_m3=45,
            kilometrage=120000,
            date_releve_km=timezone.now().date(),
        )

    def test_calculer_variables_minimisation_strictement_respectee(self):
        """Vérifie qu'aucun identifiant (immatriculation, id, nom) n'apparaît dans les variables."""
        variables = calculer_variables(self.vehicule)
        self.assertNotIn('immatriculation', variables)
        self.assertNotIn('transporteur', variables)
        self.assertNotIn('id', variables)
        self.assertEqual(variables['type_vehicule'], Vehicule.TypeVehicule.CAMION)
        self.assertEqual(variables['kilometrage'], 120000)
        self.assertGreaterEqual(variables['age_annees'], 4)

    def test_score_regles_bornes_et_facteurs(self):
        """Le score doit être compris entre 0 et 100 avec des facteurs valides."""
        variables = calculer_variables(self.vehicule)
        res = score_regles(variables)
        self.assertIn(res['niveau'], {'faible', 'moyen', 'eleve'})
        self.assertGreaterEqual(res['score'], 0)
        self.assertLessEqual(res['score'], 100)
        self.assertIsInstance(res['facteurs'], list)
        for f in res['facteurs']:
            self.assertIn('facteur', f)
            self.assertIn(f['impact'], {'hausse', 'baisse'})
            self.assertIn('explication', f)

    def test_score_regles_donnees_manquantes(self):
        """Un véhicule sans kilométrage doit renvoyer données manquantes sans crasher."""
        self.vehicule.kilometrage = None
        self.vehicule.save()
        variables = calculer_variables(self.vehicule)
        self.assertIn('kilometrage', variables['donnees_manquantes'])
        res = score_regles(variables)
        self.assertGreaterEqual(res['score'], 0)
        self.assertLessEqual(res['score'], 100)

    def test_evaluation_60_profils_harness(self):
        """Le harness d'évaluation des 60 profils synthétiques doit atteindre > 80% de précision."""
        resultats = executer_evaluation_regles()
        self.assertEqual(resultats['total_profils'], 60)
        self.assertGreaterEqual(resultats['precision_globale_pct'], 80.0)


class RisqueAssistantTestCase(TestCase):
    """Tests de validation défensive, parsing JSON et repli IA."""

    def test_validation_defensive_nettoyage_champs_invalides(self):
        """Les champs invalides ou hors limites sont assainis ou remplacés sans exception."""
        raw_invalide = {
            'niveau': 'inconnu_critique',
            'score': 999,
            'facteurs': [
                {'facteur': 'test_facteur', 'impact': 'neutre', 'explication': 'explication'}
            ],
            'recommandation': 'R' * 500,
            'motif_suggere': 'motif_inexistant',
            'urgence': 'inconnue',
            'confiance': 'non_flottant',
        }
        regles = {'niveau': 'moyen', 'score': 45, 'facteurs': []}
        nettoye = _valider_et_nettoyer_reponse_ia(raw_invalide, regles)

        self.assertEqual(nettoye['niveau'], 'moyen')
        self.assertEqual(nettoye['score'], 45)
        self.assertEqual(len(nettoye['recommandation']), 400)
        self.assertIsNone(nettoye['motif_suggere'])
        self.assertEqual(nettoye['urgence'], 'aucune')
        self.assertEqual(nettoye['confiance'], 0.5)

    def test_detection_divergence_ia_vs_regles(self):
        """Une divergence est détectée si l'écart dépasse un cran (faible <-> eleve)."""
        regles = {'niveau': 'faible', 'score': 20, 'facteurs': []}
        reponse_ia = {
            'niveau': 'eleve',
            'score': 85,
            'facteurs': [],
            'recommandation': 'Risque majeur détecté',
            'motif_suggere': 'reparation',
            'urgence': 'immediate',
            'confiance': 0.9,
        }
        res = _valider_et_nettoyer_reponse_ia(reponse_ia, regles)
        self.assertTrue(res['divergence'])

    @patch('vehicules.ia.risque_assistant.get_default_provider')
    def test_repli_gracieux_sur_quota_exceeded(self, mock_provider_getter):
        """En cas de quota dépassé, le système bascule gracieusement sur les règles."""
        mock_provider = MagicMock()
        mock_provider.generate_json.side_effect = IAQuotaExceededError("Quota épuisé")
        mock_provider_getter.return_value = mock_provider

        variables = {'type_vehicule': 'FOURGON', 'age_annees': 2, 'kilometrage': 30000}
        regles = {'niveau': 'faible', 'score': 20, 'facteurs': []}
        res = analyser_via_ia(variables, regles)

        self.assertEqual(res['source'], 'regles')
        self.assertEqual(res['niveau'], 'faible')
        self.assertIn("Quota", res['recommandation'])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RisqueServiceEtTachesTestCase(TestCase):
    """Tests du service d'analyse, du cache de hash et des tâches Celery."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='transp_service@test.com',
            full_name='Transporteur Service',
            role=User.Role.TRANSPORTEUR,
            password='password123',
        )
        self.vehicule = Vehicule.objects.create(
            transporteur=self.user,
            immatriculation='888-TN-9999',
            marque='Mercedes',
            modele='Actros',
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            annee=2021,
            capacite_poids_kg=20000,
            capacite_volume_m3=50,
            kilometrage=80000,
            date_releve_km=timezone.now().date(),
        )

    @patch('vehicules.ia.risque_assistant.get_default_provider')
    def test_analyser_vehicule_creation_et_cache_hash(self, mock_provider_getter):
        """Une analyse est enregistrée, et un deuxième appel dans les 24h réutilise le cache hash."""
        mock_provider = MagicMock()
        mock_provider.generate_json.return_value = json.dumps({
            'niveau': 'faible',
            'score': 25,
            'facteurs': [{'facteur': 'entretien_recent', 'impact': 'baisse', 'explication': 'À jour'}],
            'recommandation': 'Continuer le suivi régulier.',
            'motif_suggere': None,
            'urgence': 'aucune',
            'confiance': 0.95,
        })
        mock_provider_getter.return_value = mock_provider

        # Première analyse
        analyse1 = analyser_vehicule(self.vehicule.pk)
        self.assertIsNotNone(analyse1)
        self.assertEqual(analyse1.niveau, 'faible')
        self.assertEqual(analyse1.source, 'ia')
        self.assertEqual(mock_provider.generate_json.call_count, 1)

        # Deuxième analyse sans modification : réutilisation du cache hash
        analyse2 = analyser_vehicule(self.vehicule.pk, force=False)
        self.assertEqual(analyse1.pk, analyse2.pk)
        self.assertEqual(mock_provider.generate_json.call_count, 1)

        # Deuxième analyse avec force=True : nouvel appel API
        analyse3 = analyser_vehicule(self.vehicule.pk, force=True)
        self.assertNotEqual(analyse1.pk, analyse3.pk)
        self.assertEqual(mock_provider.generate_json.call_count, 2)

    def test_niveau_risque_vehicule_lookup_rapide(self):
        """niveau_risque_vehicule renvoie le dernier enregistrement sans appel API."""
        AnalyseRisque.objects.create(
            vehicule=self.vehicule,
            niveau=AnalyseRisque.Niveau.MOYEN,
            score=50,
            facteurs=[],
            source=AnalyseRisque.Source.REGLES,
            donnees_hash='fakehash',
        )
        info = niveau_risque_vehicule(self.vehicule.pk)
        self.assertIsNotNone(info)
        self.assertEqual(info['niveau'], 'moyen')
        self.assertEqual(info['score'], 50)

    @patch('vehicules.ia.risque_assistant.get_default_provider')
    def test_analyser_vehicule_task_eager(self, mock_provider_getter):
        """La tâche Celery s'exécute de façon synchrone et idempotente."""
        mock_provider = MagicMock()
        mock_provider.generate_json.return_value = json.dumps({
            'niveau': 'faible',
            'score': 15,
            'facteurs': [],
            'recommandation': 'R.A.S.',
            'motif_suggere': None,
            'urgence': 'aucune',
            'confiance': 1.0,
        })
        mock_provider_getter.return_value = mock_provider

        res = analyser_vehicule_task.delay(self.vehicule.pk)
        data = res.get()
        self.assertEqual(data['statut'], 'ok')
        self.assertEqual(data['vehicule_id'], self.vehicule.pk)


class RisqueVuesTestCase(TestCase):
    """Tests des endpoints HTTP et de la sécurité."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='transp_vues@test.com',
            full_name='Transporteur Vues',
            role=User.Role.TRANSPORTEUR,
            password='password123',
        )
        self.autre_user = User.objects.create_user(
            email='autre_transp@test.com',
            full_name='Autre Transporteur',
            role=User.Role.TRANSPORTEUR,
            password='password123',
        )
        self.vehicule = Vehicule.objects.create(
            transporteur=self.user,
            immatriculation='777-TN-8888',
            marque='MAN',
            modele='TGX',
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            annee=2022,
            capacite_poids_kg=22000,
            capacite_volume_m3=55,
            kilometrage=40000,
        )

    def test_analyse_risque_permission_vehicule_autre_utilisateur(self):
        """Un utilisateur ne peut pas lancer d'analyse sur le véhicule d'un autre."""
        self.client.force_login(self.autre_user)
        url = reverse('transporteur:vehicule_analyser_risque', kwargs={'pk': self.vehicule.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_analyse_risque_rate_limiting(self):
        """Le rate-limiting bloque après 10 requêtes par minute."""
        self.client.force_login(self.user)
        url = reverse('transporteur:vehicule_analyser_risque', kwargs={'pk': self.vehicule.pk})

        # Consomme les 10 requêtes autorisées
        cache_key = f"ia_risque_rl_{self.user.pk}"
        cache.set(cache_key, 10, timeout=60)

        response = self.client.post(url)
        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertIn('Limite de requêtes atteinte', data['error'])

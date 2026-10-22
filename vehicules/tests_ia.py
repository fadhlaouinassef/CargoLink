"""Tests complets pour l'assistant IA du module véhicules (Service + Endpoint)."""
import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from authentification.models import User
from vehicules.ia.assistant import AssistantDisponibilite
from vehicules.ia.providers import (
    IAConfigurationError,
    IAProviderError,
    IAQuotaExceededError,
    IATimeoutError,
    IAUnavailableError,
)
from vehicules.ia_views import RATE_LIMIT_REQUESTS
from vehicules.models import Disponibilite, Vehicule


class MockProvider:
    def __init__(self, response_text: str = "", exception_to_raise: Exception = None):
        self.response_text = response_text
        self.exception_to_raise = exception_to_raise
        self.call_count = 0
        self.last_system_prompt = None
        self.last_user_prompt = None

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if self.exception_to_raise:
            raise self.exception_to_raise
        return self.response_text


class ServiceIATestCase(TestCase):
    """Tests unitaires ciblés sur le service AssistantDisponibilite avec MockProvider."""

    def setUp(self):
        self.transporteur = User.objects.create_user(
            email='transp_ia@example.com',
            full_name='Transporteur Test',
            role=User.Role.TRANSPORTEUR,
        )
        self.autre_transporteur = User.objects.create_user(
            email='autre_ia@example.com',
            full_name='Autre Transporteur',
            role=User.Role.TRANSPORTEUR,
        )
        self.v_camion = Vehicule.objects.create(
            transporteur=self.transporteur,
            immatriculation='123 TUN 456',
            marque='Volvo',
            modele='FH',
            annee=2020,
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            capacite_poids_kg=12000,
            capacite_volume_m3=40,
            statut=Vehicule.Statut.ACTIF,
        )
        self.v_autre = Vehicule.objects.create(
            transporteur=self.autre_transporteur,
            immatriculation='999 TUN 999',
            marque='Scania',
            modele='R500',
            annee=2021,
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            capacite_poids_kg=15000,
            capacite_volume_m3=50,
            statut=Vehicule.Statut.ACTIF,
        )

    def test_json_valide_nominal(self):
        """1. JSON valide extrait nominalement avec mapping des champs."""
        json_mock = (
            '{\n'
            '  "zone_depart": "Tunis",\n'
            '  "zone_arrivee": "Sfax",\n'
            '  "date_debut": "2026-11-05T08:00",\n'
            '  "date_fin": "2026-11-08T18:00",\n'
            '  "type_vehicule": "camion",\n'
            '  "commentaire": "Disponible immédiatement",\n'
            '  "confiance": 0.95\n'
            '}'
        )
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Camion dispo Tunis à Sfax du 5 au 8 novembre", user=self.transporteur)

        self.assertTrue(res['success'])
        self.assertEqual(res['champs']['zone_depart'], "Tunis")
        self.assertEqual(res['champs']['zone_arrivee'], "Sfax")
        self.assertEqual(res['champs']['date_debut'], "2026-11-05T08:00")
        self.assertEqual(res['champs']['date_fin'], "2026-11-08T18:00")
        self.assertEqual(res['champs']['type_vehicule'], "camion")
        self.assertEqual(res['champs']['vehicule_id'], self.v_camion.id)
        self.assertEqual(len(res['champs_manquants']), 0)

    def test_markdown_codeblock_stripping(self):
        """2. Gestion des balises markdown ```json."""
        json_mock = '```json\n{"zone_depart": "Nabeul", "zone_arrivee": "Sousse", "date_debut": null, "date_fin": null, "type_vehicule": null, "commentaire": null, "confiance": 0.8}\n```'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Trajet Nabeul vers Sousse", user=self.transporteur)

        self.assertEqual(res['champs']['zone_depart'], "Nabeul")
        self.assertEqual(res['champs']['zone_arrivee'], "Sousse")
        self.assertIn('date_debut', res['champs_manquants'])
        self.assertIn('date_fin', res['champs_manquants'])

    def test_json_invalide(self):
        """3. Gestion d'un texte ne respectant pas la syntaxe JSON."""
        provider = MockProvider(response_text="Désolé je ne peux pas traiter cela")
        assistant = AssistantDisponibilite(provider=provider)
        with self.assertRaises(IAProviderError) as ctx:
            assistant.process_phrase("Camion de Tunis à Sousse", user=self.transporteur)
        self.assertEqual(ctx.exception.code, "invalid_json")

    def test_type_vehicule_hors_choix(self):
        """4. Rejet et avertissement si l'IA renvoie un type de véhicule hors liste autorisée."""
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Bizerte", "type_vehicule": "soucoupe_volante"}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Tunis à Bizerte en soucoupe", user=self.transporteur)

        self.assertIsNone(res['champs']['type_vehicule'])
        self.assertTrue(any("non reconnu" in w for w in res['avertissements']))

    def test_dates_incoherentes_date_fin_anterieure(self):
        """5. Rejet propre si la date_fin <= date_debut (règle métier CargoLink)."""
        json_mock = (
            '{\n'
            '  "zone_depart": "Tunis",\n'
            '  "zone_arrivee": "Bizerte",\n'
            '  "date_debut": "2026-11-10T18:00",\n'
            '  "date_fin": "2026-11-10T08:00"\n'
            '}'
        )
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Tunis vers Bizerte", user=self.transporteur)

        self.assertIsNone(res['champs']['date_fin'])
        self.assertTrue(any("antérieure" in w for w in res['avertissements']))

    def test_champs_inconnus_ne_plantent_pas(self):
        """6. Robustesse face à des attributs inattendus dans le JSON."""
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Sfax", "champ_inconnu": 12345}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Tunis à Sfax", user=self.transporteur)
        self.assertEqual(res['champs']['zone_depart'], "Tunis")
        self.assertNotIn("champ_inconnu", res['champs'])

    def test_isolation_entre_transporteurs(self):
        """7. Un véhicule d'un AUTRE transporteur n'est JAMAIS proposé ni sélectionné."""
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Gabès", "type_vehicule": "camion", "confiance": 0.9}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)

        sans_flotte = User.objects.create_user(
            email='vide@example.com',
            full_name='Transporteur Sans Flotte',
            role=User.Role.TRANSPORTEUR,
        )
        res = assistant.process_phrase("Camion libre Tunis vers Gabès", user=sans_flotte)

        self.assertIsNone(res['champs']['vehicule_id'])
        self.assertEqual(res['vehicules']['candidats'], [])
        self.assertIn("Aucun véhicule", res['vehicules']['message'])

    def test_resolution_0_vehicule(self):
        """8. Résolution véhicule : 0 correspondant => message explicite et vehicule_id à null."""
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Sousse", "type_vehicule": "frigorifique"}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Frigo libre Tunis", user=self.transporteur)

        self.assertIsNone(res['champs']['vehicule_id'])
        self.assertEqual(len(res['vehicules']['candidats']), 0)
        self.assertIn("Aucun véhicule actif de type 'frigorifique'", res['vehicules']['message'])

    def test_resolution_1_vehicule_automatique(self):
        """9. Résolution véhicule : 1 seul correspondant => pré-sélectionné automatiquement."""
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Sfax", "type_vehicule": "camion"}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Camion dispo", user=self.transporteur)

        self.assertEqual(res['champs']['vehicule_id'], self.v_camion.id)
        self.assertEqual(len(res['vehicules']['candidats']), 1)
        self.assertIn("sélectionné automatiquement", res['vehicules']['message'])

    def test_resolution_multiples_vehicules(self):
        """10. Résolution véhicule : plusieurs correspondants => aucun présélectionné, liste renvoyée."""
        Vehicule.objects.create(
            transporteur=self.transporteur,
            immatriculation='456 TUN 789',
            marque='Mercedes',
            modele='Actros',
            annee=2022,
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            capacite_poids_kg=18000,
            capacite_volume_m3=60,
            statut=Vehicule.Statut.ACTIF,
        )
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Sousse", "type_vehicule": "camion"}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Camion dispo Tunis Sousse", user=self.transporteur)

        self.assertIsNone(res['champs']['vehicule_id'])
        self.assertEqual(len(res['vehicules']['candidats']), 2)
        immatriculations = [c['immatriculation'] for c in res['vehicules']['candidats']]
        self.assertIn('123 TUN 456', immatriculations)
        self.assertIn('456 TUN 789', immatriculations)

    def test_vehicule_en_maintenance_ou_desactive_ignore(self):
        """11. Les véhicules en maintenance ou désactivés ne sont jamais candidats."""
        self.v_camion.statut = Vehicule.Statut.EN_MAINTENANCE
        self.v_camion.save()

        json_mock = '{"type_vehicule": "camion"}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        res = assistant.process_phrase("Camion", user=self.transporteur)

        self.assertIsNone(res['champs']['vehicule_id'])
        self.assertEqual(len(res['vehicules']['candidats']), 0)

    def test_aucune_ecriture_en_base_par_service(self):
        """12. Vérifie qu'aucun enregistrement en base n'est fait par le service."""
        count_avant = Disponibilite.objects.count()
        json_mock = '{"zone_depart": "Tunis", "zone_arrivee": "Sfax", "date_debut": "2026-11-05T08:00", "date_fin": "2026-11-08T18:00", "type_vehicule": "camion"}'
        provider = MockProvider(response_text=json_mock)
        assistant = AssistantDisponibilite(provider=provider)
        assistant.process_phrase("Camion de Tunis à Sfax", user=self.transporteur)
        self.assertEqual(Disponibilite.objects.count(), count_avant)

    def test_limite_longueur_phrase(self):
        """13. Validation de longueur minimale (3) et maximale (300)."""
        provider = MockProvider(response_text="{}")
        assistant = AssistantDisponibilite(provider=provider)
        with self.assertRaises(IAProviderError):
            assistant.process_phrase("ab", user=self.transporteur)
        with self.assertRaises(IAProviderError):
            assistant.process_phrase("x" * 301, user=self.transporteur)

    def test_gestion_timeout(self):
        """14. Propagation propre de l'erreur de timeout."""
        provider = MockProvider(exception_to_raise=IATimeoutError())
        assistant = AssistantDisponibilite(provider=provider)
        with self.assertRaises(IATimeoutError):
            assistant.process_phrase("Camion libre Tunis", user=self.transporteur)

    def test_gestion_quota_depasse(self):
        """15. Propagation propre de l'erreur de quota."""
        provider = MockProvider(exception_to_raise=IAQuotaExceededError())
        assistant = AssistantDisponibilite(provider=provider)
        with self.assertRaises(IAQuotaExceededError):
            assistant.process_phrase("Camion libre Tunis", user=self.transporteur)


class EndpointIATestCase(TestCase):
    """Tests d'intégration HTTP de l'endpoint POST /transporteur/disponibilites/ia-assistant/"""

    def setUp(self):
        cache.clear()
        self.endpoint_url = reverse('transporteur:disponibilite_ia_assistant')
        self.password = 'MotDePasse123!'

        self.transporteur = User.objects.create_user(
            email='transp_endpoint@example.com',
            password=self.password,
            full_name='Transporteur Endpoint',
            role=User.Role.TRANSPORTEUR,
        )
        self.pme = User.objects.create_user(
            email='pme_endpoint@example.com',
            password=self.password,
            full_name='PME Endpoint',
            role=User.Role.PME,
        )
        self.vehicule = Vehicule.objects.create(
            transporteur=self.transporteur,
            immatriculation='111 TUN 222',
            marque='Renault',
            modele='Master',
            annee=2021,
            type_vehicule=Vehicule.TypeVehicule.CAMIONNETTE,
            capacite_poids_kg=1500,
            capacite_volume_m3=12,
            statut=Vehicule.Statut.ACTIF,
        )

    def test_anonyme_redirige_vers_login(self):
        """16. Un utilisateur non authentifié est redirigé vers la page de login."""
        response = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette libre à Tunis"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('authentification:login'), response.url)

    def test_utilisateur_pme_refuse_404(self):
        """17. Un utilisateur avec rôle PME est refusé (Http404 via TransporteurRequiredMixin)."""
        self.client.login(email='pme_endpoint@example.com', password=self.password)
        response = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette libre à Tunis"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_methode_get_refusee(self):
        """18. Seul POST est accepté (GET doit renvoyer 405 Method Not Allowed)."""
        self.client.login(email='transp_endpoint@example.com', password=self.password)
        response = self.client.get(self.endpoint_url)
        self.assertEqual(response.status_code, 405)

    def test_protection_csrf_requise(self):
        """19. Vérifie que la protection CSRF est active (rejet si client strict sans token)."""
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(email='transp_endpoint@example.com', password=self.password)
        response = csrf_client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette libre"}),
            content_type="application/json",
        )
        # 403 Forbidden car le token CSRF n'a pas été fourni dans les en-têtes
        self.assertEqual(response.status_code, 403)

    @patch('vehicules.ia.assistant.get_default_provider')
    def test_transporteur_nominal_200(self, mock_provider_factory):
        """20. Transporteur authentifié avec CSRF : succès 200 et réponse JSON structurée."""
        json_mock = (
            '{\n'
            '  "zone_depart": "Tunis",\n'
            '  "zone_arrivee": "Bizerte",\n'
            '  "date_debut": "2026-11-01T08:00",\n'
            '  "date_fin": "2026-11-02T18:00",\n'
            '  "type_vehicule": "camionnette",\n'
            '  "confiance": 0.9\n'
            '}'
        )
        mock_provider_factory.return_value = MockProvider(response_text=json_mock)

        self.client.login(email='transp_endpoint@example.com', password=self.password)
        response = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette dispo de Tunis vers Bizerte"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['champs']['zone_depart'], "Tunis")
        self.assertEqual(data['champs']['zone_arrivee'], "Bizerte")
        self.assertEqual(data['champs']['vehicule_id'], self.vehicule.id)

    @patch('vehicules.ia.assistant.get_default_provider')
    def test_endpoint_aucune_ecriture_en_base(self, mock_provider_factory):
        """21. Vérifie STRICTEMENT qu'aucune écriture en base n'est faite par l'endpoint."""
        json_mock = (
            '{\n'
            '  "zone_depart": "Tunis",\n'
            '  "zone_arrivee": "Sousse",\n'
            '  "date_debut": "2026-11-01T08:00",\n'
            '  "date_fin": "2026-11-02T18:00",\n'
            '  "type_vehicule": "camionnette"\n'
            '}'
        )
        mock_provider_factory.return_value = MockProvider(response_text=json_mock)

        self.client.login(email='transp_endpoint@example.com', password=self.password)
        disponibilites_avant = Disponibilite.objects.count()
        vehicules_avant = Vehicule.objects.count()

        response = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette disponible pour Sousse"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Disponibilite.objects.count(), disponibilites_avant)
        self.assertEqual(Vehicule.objects.count(), vehicules_avant)

    def test_validation_longueur_phrase_400(self):
        """22. Rejet 400 si la phrase fait moins de 3 ou plus de 300 caractères."""
        self.client.login(email='transp_endpoint@example.com', password=self.password)

        res_trop_court = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "ab"}),
            content_type="application/json",
        )
        self.assertEqual(res_trop_court.status_code, 400)
        self.assertEqual(res_trop_court.json()['code'], "phrase_too_short")

        res_trop_long = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "x" * 301}),
            content_type="application/json",
        )
        self.assertEqual(res_trop_long.status_code, 400)
        self.assertEqual(res_trop_long.json()['code'], "phrase_too_long")

    @patch('vehicules.ia.assistant.get_default_provider')
    def test_limite_de_frequence_atteinte_429(self, mock_provider_factory):
        """23. Au-delà de 10 requêtes/minute pour un utilisateur, l'endpoint renvoie 429."""
        mock_provider_factory.return_value = MockProvider(response_text='{"zone_depart": "Tunis"}')
        self.client.login(email='transp_endpoint@example.com', password=self.password)

        payload = json.dumps({"phrase": "Camionnette libre Tunis"})
        for _ in range(RATE_LIMIT_REQUESTS):
            res = self.client.post(self.endpoint_url, data=payload, content_type="application/json")
            self.assertEqual(res.status_code, 200)

        # 11e requête : doit être bloquée par le rate limit
        res_bloque = self.client.post(self.endpoint_url, data=payload, content_type="application/json")
        self.assertEqual(res_bloque.status_code, 429)
        self.assertEqual(res_bloque.json()['code'], "rate_limit_exceeded")
        self.assertIn("Trop de requêtes", res_bloque.json()['error'])

    @patch('vehicules.ia.assistant.get_default_provider')
    def test_erreur_fournisseur_timeout_504(self, mock_provider_factory):
        """24. Si le provider timeout, renvoie 504 Gateway Timeout avec message clair."""
        mock_provider_factory.return_value = MockProvider(exception_to_raise=IATimeoutError())
        self.client.login(email='transp_endpoint@example.com', password=self.password)

        res = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette libre Tunis"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 504)
        self.assertEqual(res.json()['code'], "timeout")

    @patch('vehicules.ia.assistant.get_default_provider')
    def test_erreur_fournisseur_quota_exceeded_429(self, mock_provider_factory):
        """25. Si le quota de l'API externe est atteint, renvoie 429 avec message clair."""
        mock_provider_factory.return_value = MockProvider(exception_to_raise=IAQuotaExceededError())
        self.client.login(email='transp_endpoint@example.com', password=self.password)

        res = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette libre Tunis"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()['code'], "quota_exceeded")

    @patch('vehicules.ia.assistant.get_default_provider')
    def test_erreur_fournisseur_indisponible_503(self, mock_provider_factory):
        """26. Si le service est indisponible ou mal configuré, renvoie 503."""
        mock_provider_factory.return_value = MockProvider(exception_to_raise=IAUnavailableError())
        self.client.login(email='transp_endpoint@example.com', password=self.password)

        res = self.client.post(
            self.endpoint_url,
            data=json.dumps({"phrase": "Camionnette libre Tunis"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()['code'], "unavailable")


class FrontIATestCase(TestCase):
    """Tests du composant Front IA et de son accessibilité dans la page véhicules."""

    def setUp(self):
        self.password = 'MotDePasse123!'
        self.transporteur = User.objects.create_user(
            email='transp_front@example.com',
            password=self.password,
            full_name='Transporteur Front',
            role=User.Role.TRANSPORTEUR,
        )
        self.pme = User.objects.create_user(
            email='pme_front@example.com',
            password=self.password,
            full_name='PME Front',
            role=User.Role.PME,
        )
        self.page_url = reverse('transporteur:vehicules')

    def test_transporteur_voit_composant_ia_avec_accessibilite(self):
        """27. Le transporteur voit le composant IA avec les balises d'accessibilité WCAG AA."""
        self.client.login(email='transp_front@example.com', password=self.password)
        response = self.client.get(self.page_url)
        self.assertEqual(response.status_code, 200)

        # Vérification des éléments d'accessibilité WCAG AA
        self.assertContains(response, 'id="assistant-ia-container"')
        self.assertContains(response, 'id="assistant-ia-phrase"')
        self.assertContains(response, 'id="assistant-ia-submit"')
        self.assertContains(response, 'aria-describedby="assistant-ia-help assistant-ia-counter"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, 'Remplir avec l’IA')
        self.assertContains(response, 'assistant_ia.js')
        self.assertContains(response, 'assistant_ia.css')

    def test_utilisateur_non_transporteur_ne_voit_pas_composant_ia(self):
        """28. Un utilisateur non transporteur (ex: PME) n'a pas accès à la vue (404)."""
        self.client.login(email='pme_front@example.com', password=self.password)
        response = self.client.get(self.page_url)
        self.assertEqual(response.status_code, 404)


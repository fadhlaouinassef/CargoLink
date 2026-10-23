import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from demandes.models import DemandeTransport
from .models import OffreTransport, Trajet
from .services import (
    RapportErreur, generer_analyse_ia, generer_pdf_rapport, preparer_donnees_rapport,
)


ANALYSE = {
    'synthese': 'Ce trajet présente des offres décidées. Les montants sont proposés.',
    'analyse_acceptees': 'Les offres acceptées représentent un engagement commercial.',
    'analyse_refusees': 'Les motifs de refus ne sont pas renseignés.',
    'recommandations': ['Vérifier la planification du trajet.', 'Demander les motifs de refus.'],
}


class RapportTrajetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.carrier = users.create_user(email='rapport@example.com', role='transporteur')
        cls.other = users.create_user(email='autre-rapport@example.com', role='transporteur')
        cls.pme = users.create_user(email='pme-rapport@example.com', role='PME')
        depart = timezone.now() + timedelta(days=1)
        cls.trajet = Trajet.objects.create(
            transporteur=cls.carrier, depart_ville='Tunis', arrivee_ville='Sfax',
            date_depart=depart, vehicule='123 TU 456', capacite_kg=1000, volume_m3=10,
        )
        cls.offres = []
        for index, (statut, prix) in enumerate([
            ('acceptee', '250.10'), ('refusee', '180.20'), ('en_attente', '999.00'),
        ]):
            demande = DemandeTransport.objects.create(
                created_by=cls.pme, depart_ville='Tunis', arrivee_ville='Sfax',
                date_depart=depart.date(), date_limite=depart.date(),
                destinataire_nom='Donnée privée', destinataire_tel='12345678',
            )
            cls.offres.append(OffreTransport.objects.create(
                trajet=cls.trajet, demande=demande, transporteur=cls.carrier,
                prix=prix, statut=statut, message=f'Message {index}',
            ))

    def setUp(self):
        self.client.force_login(self.carrier)
        self.url = reverse('transporteur:trajet_rapport', args=[self.trajet.pk])

    def test_data_only_contains_owned_decided_offers_and_exact_totals(self):
        donnees = preparer_donnees_rapport(self.trajet)
        self.assertEqual(donnees['indicateurs']['total_accepte_tnd'], '250.10')
        self.assertEqual(donnees['indicateurs']['total_refuse_tnd'], '180.20')
        self.assertEqual(donnees['indicateurs']['taux_acceptation'], '50.0')
        texte = json.dumps(donnees)
        self.assertNotIn('999.00', texte)
        self.assertNotIn('Donnée privée', texte)
        self.assertNotIn('destinataire_tel', texte)
        self.offres[0].transporteur = self.other
        self.offres[0].save()
        self.assertEqual(preparer_donnees_rapport(self.trajet)['offres']['acceptees'], [])

    def test_empty_trip_has_no_division_by_zero(self):
        self.trajet.offres.all().update(statut='en_attente')
        data = preparer_donnees_rapport(self.trajet)
        self.assertIsNone(data['indicateurs']['taux_acceptation'])
        self.assertEqual(data['indicateurs']['total_accepte_tnd'], '0.00')

    @patch('gestion_trajets_offres.views.generer_pdf_rapport', return_value=b'%PDF-1.4 test')
    def test_download_button_and_response(self, generate):
        self.assertContains(self.client.get(reverse('transporteur:trajets')), 'Générer Rapport')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'rapport-trajet-{self.trajet.pk}.pdf', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        generate.assert_called_once()

    @patch('gestion_trajets_offres.views.generer_pdf_rapport')
    def test_access_method_and_csrf_prevent_api_calls(self, generate):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.carrier)
        self.assertEqual(csrf_client.post(self.url).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.client.force_login(self.pme)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        generate.assert_not_called()

    @patch('gestion_trajets_offres.views.generer_pdf_rapport', side_effect=RapportErreur('Clé manquante'))
    def test_service_error_is_presented(self, generate):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'error': 'Clé manquante'})

    @patch.dict('os.environ', {'GEMINI_RAPPORT_API_KEY': ''})
    @patch('gestion_trajets_offres.services.urlopen')
    def test_missing_key_does_not_call_api(self, api):
        with self.assertRaisesMessage(RapportErreur, 'GEMINI_RAPPORT_API_KEY'):
            generer_analyse_ia({})
        api.assert_not_called()

    @patch.dict('os.environ', {'GEMINI_RAPPORT_API_KEY': 'test-key', 'GEMINI_RAPPORT_MODEL': 'gemini-3.1-flash-lite'})
    @patch('gestion_trajets_offres.services.urlopen')
    def test_gemini_payload_and_validated_response(self, api):
        api.return_value.__enter__.return_value = BytesIO(json.dumps({
            'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'text': 'Réflexion interne', 'thought': True}, {'text': json.dumps(ANALYSE)},
            ]}}],
        }).encode())
        data = preparer_donnees_rapport(self.trajet)
        self.assertEqual(generer_analyse_ia(data), ANALYSE)
        request = api.call_args.args[0]
        self.assertEqual(request.full_url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent')
        self.assertEqual(request.get_header('X-goog-api-key'), 'test-key')
        self.assertNotIn('test-key', request.full_url)
        body = json.loads(request.data)
        self.assertEqual(json.loads(body['contents'][0]['parts'][0]['text']), data)
        self.assertIn('systemInstruction', body)
        self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
        self.assertEqual(body['generationConfig']['thinkingConfig'], {'thinkingLevel': 'low'})
        self.assertEqual(api.call_args.kwargs['timeout'], 60)

    @patch.dict('os.environ', {'GEMINI_RAPPORT_API_KEY': 'test-key'})
    @patch('gestion_trajets_offres.services.urlopen')
    def test_api_failures_and_invalid_content(self, api):
        for error in [URLError('timeout'), HTTPError('url', 401, 'Secret', {}, None),
                      HTTPError('url', 400, 'Secret', {}, None), HTTPError('url', 403, 'Secret', {}, None),
                      HTTPError('url', 404, 'Secret', {}, None), HTTPError('url', 429, 'Secret', {}, None)]:
            with self.subTest(error=error):
                api.side_effect = error
                with self.assertRaises(RapportErreur):
                    generer_analyse_ia({})
        api.side_effect = None
        for payload in [{}, {'candidates': []}, {'candidates': [{'finishReason': 'MAX_TOKENS'}]},
                        {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{}'}]}}]}]:
            api.return_value.__enter__.return_value = BytesIO(json.dumps(payload).encode())
            with self.assertRaises(RapportErreur):
                generer_analyse_ia({})

    @patch('gestion_trajets_offres.services.generer_analyse_ia', return_value=ANALYSE)
    def test_real_pdf_contains_logo_tables_and_no_pending_offer(self, analyse):
        pdf = generer_pdf_rapport(self.trajet)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        reader = PdfReader(BytesIO(pdf))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for expected in ['CargoLink', '250.10', '180.20', 'Offres acceptées', 'Offres refusées']:
            self.assertIn(expected, text)
        self.assertNotIn('999.00', text)
        self.assertGreater(len(reader.pages[0].images), 0)

    @patch('gestion_trajets_offres.services.generer_analyse_ia', return_value=ANALYSE)
    def test_empty_pdf_and_escaped_ai_text(self, analyse):
        self.trajet.offres.all().update(statut='en_attente')
        analyse.return_value = {**ANALYSE, 'synthese': '<b>Texte non interprété</b>'}
        reader = PdfReader(BytesIO(generer_pdf_rapport(self.trajet)))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('Aucune offre acceptée', text)
        self.assertIn('Aucune offre refusée', text)
        self.assertIn('<b>Texte non interprété</b>', text)

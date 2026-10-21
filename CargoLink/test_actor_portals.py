from django.test import SimpleTestCase
from django.urls import reverse


class ActorPortalsTests(SimpleTestCase):
    def test_transporteur_portal_urls(self):
        for page in ('dashboard', 'trajets', 'offres', 'vehicules', 'transports', 'avis'):
            with self.subTest(page=page):
                response = self.client.get(reverse(f'transporteur:{page}'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Espace transporteur')
                self.assertContains(response, 'Données fictives')

    def test_pme_portal_urls(self):
        urls = [
            'pme:dashboard',
            'pme:demandes_list',
            'pme:demande_create',
            'pme:demande_detail',
            'pme:offres_comparer',
            'pme:transports_list',
            'pme:transport_suivi',
            'pme:avis_create',
            'pme:reclamation_create',
        ]
        for url_name in urls:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_destinataire_portal_urls(self):
        urls = [
            'destinataire:dashboard',
            'destinataire:suivi',
            'destinataire:confirmation',
            'destinataire:reclamation',
        ]
        for url_name in urls:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_homepage_loads(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

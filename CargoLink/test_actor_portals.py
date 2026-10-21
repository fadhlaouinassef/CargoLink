from django.test import TestCase
from django.urls import reverse

from authentification.models import User

class ActorPortalsTests(TestCase):
    def setUp(self):
        self.transporteur = User.objects.create_user(
            email='portal@example.com',
            password='Strong-password-872!',
            full_name='Transporteur Portal',
            role=User.Role.TRANSPORTEUR,
        )

    def test_transporteur_portal_urls(self):
        for page in ('dashboard', 'trajets', 'demandes', 'offres', 'vehicules', 'transports', 'avis'):
            with self.subTest(page=page):
                if page == 'vehicules':
                    self.client.force_login(self.transporteur)
                response = self.client.get(reverse(f'transporteur:{page}'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Espace transporteur')
                if page != 'vehicules':
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

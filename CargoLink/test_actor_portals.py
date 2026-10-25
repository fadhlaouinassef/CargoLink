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
        # La page « avis » est réelle et protégée : voir avis_reclamations/tests.py.
        self.client.force_login(self.transporteur)
        for page in ('dashboard', 'trajets', 'offres', 'vehicules', 'transports'):
            with self.subTest(page=page):
                response = self.client.get(reverse(f'transporteur:{page}'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Espace transporteur')
                if page not in ('vehicules', 'transports'):
                    self.assertContains(response, 'Données fictives')

    def test_pme_portal_urls(self):
        pme = User.objects.create_user(
            email='portal-pme@example.com',
            password='Strong-password-872!',
            full_name='PME Portal',
            role=User.Role.PME,
        )
        self.client.force_login(pme)
        urls = [
            'pme:dashboard',
            'pme:demandes_list',
            'pme:demande_create',
            'pme:demande_detail',
            'pme:offres_comparer',
            'pme:transports_list',
            'pme:transport_suivi',
        ]
        for url_name in urls:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_destinataire_portal_urls(self):
        destinataire = User.objects.create_user(
            email='recipient@example.com',
            password='Strong-password-872!',
            full_name='Destinataire Portal',
            role=User.Role.DESTINATAIRE,
        )
        self.client.force_login(destinataire)
        urls = [
            'destinataire:dashboard',
            'destinataire:suivi',
            'destinataire:confirmation',
        ]
        for url_name in urls:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_portails_refusent_les_comptes_d_un_autre_role(self):
        pme = User.objects.create_user(
            email='role-pme@example.com',
            password='Strong-password-872!',
            full_name='PME',
            role=User.Role.PME,
        )
        destinataire = User.objects.create_user(
            email='role-recipient@example.com',
            password='Strong-password-872!',
            full_name='Destinataire',
            role=User.Role.DESTINATAIRE,
        )
        pme_urls = [
            reverse('pme:dashboard'),
            reverse('pme:demandes_list'),
            reverse('pme:demande_create'),
            reverse('pme:offres_comparer'),
            reverse('pme:transports_list'),
            reverse('pme:demande_offres', args=[999999]),
        ]
        for user in (self.transporteur, destinataire):
            self.client.force_login(user)
            for url in pme_urls:
                with self.subTest(role=user.role, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(
                self.client.post(
                    reverse('pme:ai_improve_description'),
                    data='{}',
                    content_type='application/json',
                ).status_code,
                403,
            )

        destinataire_urls = [
            reverse('destinataire:dashboard'),
            reverse('destinataire:suivi'),
            reverse('destinataire:confirmation'),
        ]
        for user in (self.transporteur, pme):
            self.client.force_login(user)
            for url in destinataire_urls:
                with self.subTest(role=user.role, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_homepage_loads(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

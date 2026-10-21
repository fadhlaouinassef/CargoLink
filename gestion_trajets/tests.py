from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from demandes.models import DemandeTransport, Marchandise
from .models import OffreTransport, Trajet


class GestionTrajetsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.carrier = users.create_user(email='carrier@example.com', role='transporteur')
        cls.other = users.create_user(email='other@example.com', role='transporteur')
        cls.pme = users.create_user(email='pme@example.com', role='PME')
        cls.depart = timezone.now() + timedelta(days=3)
        cls.demande = DemandeTransport.objects.create(
            created_by=cls.pme, depart_ville='Tunis', depart_adresse='Dépôt A',
            arrivee_ville='Sfax', arrivee_adresse='Dépôt B',
            date_depart=cls.depart.date(), date_limite=cls.depart.date() + timedelta(days=2),
            destinataire_nom='Client', destinataire_contact='Contact', destinataire_tel='12345678',
        )
        Marchandise.objects.create(demande=cls.demande, description='Palettes de cartons', poids=100, volume=2)
        cls.trajet = Trajet.objects.create(
            transporteur=cls.carrier, depart_ville='Tunis', arrivee_ville='Sfax',
            date_depart=cls.depart, vehicule='123 TU 456', capacite_kg=1000, volume_m3=10,
        )

    def setUp(self):
        self.client.force_login(self.carrier)

    def url(self, name, *args):
        return reverse(f'transporteur:{name}', args=args)

    def test_only_transporteurs_can_access_module(self):
        routes = [self.url(name) for name in ['demandes', 'trajets', 'offres', 'transports']]
        routes += [self.url('trajet_create'), self.url('offre_create', self.demande.pk), self.url('trajet_suivi', self.trajet.pk)]
        self.client.logout()
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.pme)
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_list_only_open_pme_demands_and_search(self):
        response = self.client.get(self.url('demandes'), {'q': 'cartons'})
        self.assertContains(response, 'Postuler')
        self.assertEqual(list(response.context['demandes']), [self.demande])
        self.demande.statut = 'brouillon'
        self.demande.save()
        self.assertNotContains(self.client.get(self.url('demandes')), str(self.demande))
        self.assertEqual(self.client.get(self.url('offre_create', self.demande.pk)).status_code, 404)
        self.demande.statut = 'ouverte'
        self.demande.created_by = self.other
        self.demande.save()
        self.assertEqual(self.client.get(self.url('demande_detail', self.demande.pk)).status_code, 404)

    def test_offer_popup_create_update_duplicate_and_confirm_delete(self):
        url = self.url('offre_create', self.demande.pk)
        self.assertIn('data-module-form', self.client.get(url).json()['html'])
        data = {'trajet': self.trajet.pk, 'prix': '250.00', 'message': 'Disponible'}
        self.assertEqual(self.client.post(url, data).json(), {'success': True})
        offre = OffreTransport.objects.get()
        self.assertEqual(offre.transporteur, self.carrier)
        self.assertEqual(self.client.post(url, data).status_code, 422)
        data['prix'] = '275.00'
        self.assertEqual(self.client.post(self.url('offre_update', offre.pk), data).status_code, 200)
        offre.refresh_from_db()
        self.assertEqual(str(offre.prix), '275.00')
        delete_url = self.url('offre_delete', offre.pk)
        self.assertIn('Confirmer la suppression', self.client.get(delete_url).json()['html'])
        self.assertTrue(OffreTransport.objects.filter(pk=offre.pk).exists())
        self.assertEqual(self.client.post(delete_url).json(), {'success': True})
        self.assertFalse(OffreTransport.objects.exists())

    def test_cannot_access_another_carriers_records(self):
        offre = OffreTransport.objects.create(transporteur=self.carrier, demande=self.demande, trajet=self.trajet, prix=200)
        self.client.force_login(self.other)
        for name, pk in [('trajet_update', self.trajet.pk), ('trajet_delete', self.trajet.pk),
                         ('trajet_suivi', self.trajet.pk), ('offre_update', offre.pk), ('offre_delete', offre.pk)]:
            self.assertEqual(self.client.get(self.url(name, pk)).status_code, 404)
            self.assertEqual(self.client.post(self.url(name, pk), {}).status_code, 404)
        self.assertNotContains(self.client.get(self.url('transports')), self.trajet.vehicule)

    def test_offer_rejects_foreign_trajet_and_insufficient_capacity(self):
        url = self.url('offre_create', self.demande.pk)
        self.trajet.transporteur = self.other
        self.trajet.save()
        self.assertEqual(self.client.post(url, {'trajet': self.trajet.pk, 'prix': 200}).status_code, 422)
        self.trajet.transporteur = self.carrier
        self.trajet.capacite_kg = 10
        self.trajet.save()
        self.assertEqual(self.client.post(url, {'trajet': self.trajet.pk, 'prix': 200}).status_code, 422)
        self.assertFalse(OffreTransport.objects.exists())

    def test_trajet_crud_and_tracking_persist(self):
        data = {'depart_ville': 'Sousse', 'arrivee_ville': 'Bizerte',
                'date_depart': self.depart.strftime('%Y-%m-%dT%H:%M'), 'vehicule': 'Camion',
                'capacite_kg': 500, 'volume_m3': 5, 'statut': 'publie'}
        self.assertEqual(self.client.post(self.url('trajet_create'), data).json(), {'success': True})
        trajet = Trajet.objects.get(vehicule='Camion')
        data['vehicule'] = 'Camion B'
        self.assertEqual(self.client.post(self.url('trajet_update', trajet.pk), data).status_code, 200)
        self.assertEqual(self.client.post(self.url('trajet_suivi', trajet.pk), {'statut': 'en_cours'}).json(), {'success': True})
        trajet.refresh_from_db()
        self.assertEqual(trajet.statut, 'en_cours')
        self.assertContains(self.client.get(self.url('transports')), 'Camion B')
        self.assertEqual(self.client.post(self.url('trajet_delete', trajet.pk)).status_code, 200)
        self.assertFalse(Trajet.objects.filter(pk=trajet.pk).exists())

    def test_accepted_offers_and_linked_trajets_are_protected(self):
        offre = OffreTransport.objects.create(transporteur=self.carrier, demande=self.demande,
                                             trajet=self.trajet, prix=200, statut='acceptee')
        self.assertEqual(self.client.post(self.url('offre_delete', offre.pk)).status_code, 409)
        self.assertEqual(self.client.get(self.url('offre_update', offre.pk)).status_code, 409)
        self.assertEqual(self.client.post(self.url('trajet_delete', self.trajet.pk)).status_code, 409)

    def test_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.carrier)
        self.assertEqual(client.post(self.url('trajet_create'), {}).status_code, 403)

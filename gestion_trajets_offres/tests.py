from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from demandes.models import DemandeTransport, Marchandise
from vehicules.models import Vehicule
from .models import OffreTransport, Trajet


class GestionTrajetsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.carrier = users.create_user(email='carrier@example.com', role='transporteur')
        cls.other = users.create_user(email='other@example.com', role='transporteur')
        cls.pme = users.create_user(email='pme@example.com', role='PME')
        cls.depart = timezone.now() + timedelta(days=3)
        cls.vehicule = Vehicule.objects.create(
            transporteur=cls.carrier, immatriculation='123 TU 456', marque='Iveco',
            modele='Daily', annee=2024, type_vehicule='camion',
            capacite_poids_kg=1000, capacite_volume_m3=10,
        )
        cls.other_vehicule = Vehicule.objects.create(
            transporteur=cls.other, immatriculation='789 TU 123', marque='Renault',
            modele='Master', annee=2024, type_vehicule='camionnette',
            capacite_poids_kg=500, capacite_volume_m3=5,
        )
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
                'date_depart': self.depart.strftime('%Y-%m-%dT%H:%M'), 'vehicule': self.vehicule.immatriculation,
                'capacite_kg': 500, 'volume_m3': 5, 'statut': 'publie'}
        self.assertEqual(self.client.post(self.url('trajet_create'), data).json(), {'success': True})
        trajet = Trajet.objects.get(depart_ville='Sousse')
        self.assertEqual(trajet.capacite_kg, self.vehicule.capacite_poids_kg)
        self.assertEqual(trajet.volume_m3, self.vehicule.capacite_volume_m3)
        data['arrivee_ville'] = 'Gabes'
        self.assertEqual(self.client.post(self.url('trajet_update', trajet.pk), data).status_code, 200)
        self.assertEqual(self.client.post(self.url('trajet_suivi', trajet.pk), {'statut': 'en_cours'}).json(), {'success': True})
        trajet.refresh_from_db()
        self.assertEqual(trajet.statut, 'en_cours')
        self.assertEqual(trajet.arrivee_ville, 'Gabes')
        self.assertContains(self.client.get(self.url('transports')), self.vehicule.immatriculation)
        self.assertEqual(self.client.post(self.url('trajet_delete', trajet.pk)).status_code, 200)
        self.assertFalse(Trajet.objects.filter(pk=trajet.pk).exists())

    def test_trajet_popup_only_lists_owned_vehicles_with_capacity(self):
        self.assertContains(
            self.client.get(self.url('trajets')),
            '/static/gestion_trajets_offres/trajet.js',
        )
        html = self.client.get(self.url('trajet_create')).json()['html']
        self.assertIn(str(self.vehicule), html)
        self.assertNotIn(self.other_vehicule.immatriculation, html)
        self.assertIn('data-capacite="1000.00"', html)
        self.assertIn('data-volume="10.00"', html)
        self.assertRegex(html, r'<input[^>]*name="capacite_kg"[^>]* disabled')
        self.assertRegex(html, r'<input[^>]*name="volume_m3"[^>]* disabled')

    def test_trajet_requires_owned_vehicle_and_ignores_posted_capacity(self):
        data = {
            'depart_ville': 'Sousse', 'arrivee_ville': 'Bizerte',
            'date_depart': self.depart.strftime('%Y-%m-%dT%H:%M'), 'statut': 'publie',
        }
        url = self.url('trajet_create')
        for value in ('', 'Camion libre', self.other_vehicule.immatriculation):
            self.assertEqual(self.client.post(url, {**data, 'vehicule': value}).status_code, 422)
        data['vehicule'] = self.vehicule.immatriculation
        self.assertEqual(self.client.post(url, data).json(), {'success': True})
        trajet = Trajet.objects.get(depart_ville='Sousse')
        self.other_vehicule.transporteur = self.carrier
        self.other_vehicule.save()
        data['vehicule'] = self.other_vehicule.immatriculation
        response = self.client.post(self.url('trajet_update', trajet.pk), {
            **data, 'capacite_kg': 999999, 'volume_m3': 999999,
        })
        self.assertEqual(response.json(), {'success': True})
        trajet.refresh_from_db()
        self.assertEqual(trajet.vehicule, self.other_vehicule.immatriculation)
        self.assertEqual(trajet.capacite_kg, self.other_vehicule.capacite_poids_kg)
        self.assertEqual(trajet.volume_m3, self.other_vehicule.capacite_volume_m3)

    def test_trajet_without_owned_vehicles_cannot_be_created(self):
        self.vehicule.delete()
        html = self.client.get(self.url('trajet_create')).json()['html']
        self.assertNotIn('data-capacite=', html)
        response = self.client.post(self.url('trajet_create'), {
            'depart_ville': 'Sousse', 'arrivee_ville': 'Bizerte',
            'date_depart': self.depart.strftime('%Y-%m-%dT%H:%M'),
            'vehicule': self.other_vehicule.immatriculation, 'statut': 'publie',
        })
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Trajet.objects.filter(depart_ville='Sousse').exists())

    def test_accepted_trajet_only_allows_status_updates(self):
        OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet,
            prix=200, statut='acceptee',
        )
        data = {
            'depart_ville': 'Tunis', 'arrivee_ville': 'Sfax',
            'date_depart': self.depart.strftime('%Y-%m-%dT%H:%M'),
            'vehicule': self.vehicule.immatriculation, 'statut': 'en_cours',
        }
        # Use the exact stored departure so this remains a status-only update.
        self.trajet.date_depart = self.depart.replace(second=0, microsecond=0)
        self.trajet.save()
        url = self.url('trajet_update', self.trajet.pk)
        self.assertEqual(self.client.post(url, data).json(), {'success': True})
        self.vehicule.capacite_poids_kg = 800
        self.vehicule.save()
        self.assertEqual(self.client.post(url, data).status_code, 422)
        self.trajet.refresh_from_db()
        self.assertEqual(self.trajet.capacite_kg, 1000)

    def test_trajet_edit_preserves_vehicle_selection_and_capacity_after_error(self):
        url = self.url('trajet_update', self.trajet.pk)
        html = self.client.get(url).json()['html']
        self.assertIn('value="123 TU 456" selected', html)
        response = self.client.post(url, {
            'depart_ville': 'Tunis', 'arrivee_ville': 'Tunis',
            'date_depart': self.depart.strftime('%Y-%m-%dT%H:%M'),
            'vehicule': self.vehicule.immatriculation, 'statut': 'publie',
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn('value="1000.00"', response.json()['html'])
        self.assertIn('value="10.00"', response.json()['html'])

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

    def test_pme_can_read_only_their_demand_offers(self):
        OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet,
            prix=200, message='<script>alert(1)</script>',
        )
        url = reverse('pme:demande_offres', args=[self.demande.pk])
        self.client.force_login(self.pme)
        html = self.client.get(url).json()['html']
        self.assertIn(reverse('pme:offres_classees', args=[self.demande.pk]), html)
        self.assertIn('Chargement du classement des offres', html)
        self.assertNotIn(self.carrier.email, html)
        self.assertNotIn('<script>', html)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_pme_offers_popup_empty_and_button(self):
        self.client.force_login(self.pme)
        url = reverse('pme:demande_offres', args=[self.demande.pk])
        self.assertContains(self.client.get(reverse('pme:demandes_list')), f'data-popup-url="{url}"')
        popup = self.client.get(url).json()['html']
        self.assertIn('data-ranking-url=', popup)
        self.assertIn('Chargement du classement des offres', popup)

    def test_model_failure_returns_manual_comparison_without_score(self):
        offre = OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet, prix=200,
        )
        self.client.force_login(self.pme)
        fake_service = SimpleNamespace(evaluate_and_rank_offres=Mock(side_effect=RuntimeError('model unavailable')))
        with patch.dict('sys.modules', {'matching_des_offres.services': fake_service}):
            response = self.client.get(reverse('pme:offres_classees', args=[self.demande.pk]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['statut'], 'modele_indisponible')
        self.assertEqual(len(data['offres_secours']), 1)
        fallback = data['offres_secours'][0]
        self.assertIsNone(fallback['score'])
        self.assertIsNone(fallback['rang'])
        self.assertTrue(fallback['url_accepter'].endswith(f'/offres/{offre.pk}/accepter/'))

    def test_session_owner_can_read_their_demand_offers(self):
        self.client.logout()
        session = self.client.session
        session.save()
        self.demande.created_by = None
        self.demande.owner_session = session.session_key
        self.demande.save()
        url = reverse('pme:demande_offres', args=[self.demande.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Client().get(url).status_code, 404)

    def test_accept_offer_updates_popup_and_rejects_other_offers(self):
        offre = OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet, prix=200,
        )
        other = OffreTransport.objects.create(
            transporteur=self.other, demande=self.demande, trajet=self.trajet, prix=250,
        )
        self.client.force_login(self.pme)
        url = reverse('pme:accepter_offre', args=[self.demande.pk, offre.pk])
        popup_url = reverse('pme:demande_offres', args=[self.demande.pk])
        self.assertIn(reverse('pme:offres_classees', args=[self.demande.pk]),
                      self.client.get(popup_url).json()['html'])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-ranking-url=', response.json()['html'])
        offre.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(offre.statut, OffreTransport.Statut.ACCEPTEE)
        self.assertEqual(other.statut, OffreTransport.Statut.REFUSEE)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(self.client.post(reverse('pme:accepter_offre', args=[self.demande.pk, other.pk])).status_code, 409)
        self.client.force_login(self.carrier)
        self.assertEqual(self.client.get(self.url('offre_create', self.demande.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url('offre_update', offre.pk)).status_code, 409)

    def test_accept_offer_checks_owner_demand_status_and_csrf(self):
        offre = OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet, prix=200,
        )
        url = reverse('pme:accepter_offre', args=[self.demande.pk, offre.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.pme)
        self.assertEqual(self.client.post(reverse('pme:accepter_offre', args=[self.demande.pk, offre.pk + 1])).status_code, 404)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.pme)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        self.demande.statut = DemandeTransport.Statut.BROUILLON
        self.demande.save()
        self.assertEqual(self.client.post(url).status_code, 409)
        offre.refresh_from_db()
        self.assertEqual(offre.statut, OffreTransport.Statut.EN_ATTENTE)

    def test_accept_offer_rechecks_route_vehicle_and_capacities(self):
        offre = OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet, prix=200,
        )
        self.client.force_login(self.pme)
        url = reverse('pme:accepter_offre', args=[self.demande.pk, offre.pk])

        self.vehicule.capacite_poids_kg = 50
        self.vehicule.save()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 409)
        offre.refresh_from_db()
        self.assertEqual(offre.statut, OffreTransport.Statut.EN_ATTENTE)

        self.vehicule.capacite_poids_kg = 1000
        self.vehicule.save()
        self.trajet.statut = Trajet.Statut.ANNULE
        self.trajet.save()
        self.assertEqual(self.client.post(url).status_code, 409)
        offre.refresh_from_db()
        self.assertEqual(offre.statut, OffreTransport.Statut.EN_ATTENTE)

    def test_accept_offer_rejects_vehicle_unavailability_and_duplicate_booking(self):
        from vehicules.models import Disponibilite

        unavailable_offer = OffreTransport.objects.create(
            transporteur=self.carrier, demande=self.demande, trajet=self.trajet, prix=200,
        )
        Disponibilite.objects.create(
            vehicule=self.vehicule,
            date_debut=self.depart.replace(hour=0, minute=0),
            date_fin=self.depart.replace(hour=0, minute=0) + timedelta(days=1),
            zone_depart='Tunis', zone_arrivee='Sfax', statut=Disponibilite.Statut.INDISPONIBLE,
        )
        self.client.force_login(self.pme)
        url = reverse('pme:accepter_offre', args=[self.demande.pk, unavailable_offer.pk])
        self.assertEqual(self.client.post(url).status_code, 409)
        unavailable_offer.refresh_from_db()
        self.assertEqual(unavailable_offer.statut, OffreTransport.Statut.EN_ATTENTE)

        # Le même véhicule ne peut pas être confirmé deux fois sur sa journée de départ.
        Disponibilite.objects.all().delete()
        booked_demand = DemandeTransport.objects.create(
            created_by=self.pme, depart_ville='Tunis', depart_adresse='A',
            arrivee_ville='Sfax', arrivee_adresse='B',
            date_depart=self.depart.date(), date_limite=self.depart.date() + timedelta(days=2),
            destinataire_nom='Client', destinataire_contact='Contact', destinataire_tel='12345678',
        )
        Marchandise.objects.create(demande=booked_demand, description='Palette', poids=100, volume=2)
        booked_offer = OffreTransport.objects.create(
            transporteur=self.carrier, demande=booked_demand, trajet=self.trajet,
            prix=200, statut=OffreTransport.Statut.ACCEPTEE,
        )
        self.assertEqual(booked_offer.statut, OffreTransport.Statut.ACCEPTEE)
        self.assertEqual(self.client.post(url).status_code, 409)

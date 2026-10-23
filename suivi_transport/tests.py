from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from demandes.models import DemandeTransport
from gestion_trajets_offres.models import OffreTransport, Trajet

from .models import EvenementSuivi, Transport


class SuiviTransportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.pme = users.create_user(email='suivi-pme@example.com', password='Strong-password-872!', role='PME')
        cls.other_pme = users.create_user(email='suivi-other@example.com', password='Strong-password-872!', role='PME')
        cls.carrier = users.create_user(email='suivi-carrier@example.com', password='Strong-password-872!', role='transporteur')
        depart = timezone.now() + timedelta(days=3)
        cls.demande = DemandeTransport.objects.create(
            created_by=cls.pme, depart_ville='Tunis', depart_adresse='Dépôt A', date_depart=depart.date(),
            arrivee_ville='Sfax', arrivee_adresse='Dépôt B', date_limite=depart.date() + timedelta(days=2),
            destinataire_nom='Client', destinataire_contact='Contact', destinataire_tel='12345678',
        )
        trajet = Trajet.objects.create(
            transporteur=cls.carrier, depart_ville='Tunis', arrivee_ville='Sfax', date_depart=depart,
            vehicule='123 TU 456', capacite_kg=1000, volume_m3=10,
        )
        cls.offre = OffreTransport.objects.create(
            transporteur=cls.carrier, demande=cls.demande, trajet=trajet, prix=200,
        )

    def test_accepting_offer_creates_one_transport(self):
        self.client.force_login(self.pme)
        url = reverse('pme:accepter_offre', args=[self.demande.pk, self.offre.pk])
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(Transport.objects.filter(offre=self.offre).count(), 1)
        transport = Transport.objects.get(offre=self.offre)
        self.assertEqual(transport.evenements.get().statut, Transport.Statut.PLANIFIE)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(Transport.objects.filter(offre=self.offre).count(), 1)

    def test_pme_access_is_scoped_to_owned_demand(self):
        transport = Transport.objects.create(offre=self.offre)
        self.client.force_login(self.pme)
        response = self.client.get(reverse('pme:transports_list'))
        self.assertContains(response, str(transport))
        self.assertContains(response, 'Sfax')
        self.assertNotContains(response, '{{ transport.')
        self.client.force_login(self.other_pme)
        self.assertNotContains(self.client.get(reverse('pme:transports_list')), str(transport))
        self.assertEqual(self.client.get(reverse('pme:transport_detail', args=[transport.pk])).status_code, 404)

    def test_transport_can_be_deleted_only_by_its_carrier_before_tracking(self):
        transport = Transport.objects.create(offre=self.offre)
        self.client.force_login(self.other_pme)
        url = reverse('transporteur:transport_delete', args=[transport.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.carrier)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Transport.objects.filter(pk=transport.pk).exists())

    def test_carrier_event_and_pme_receipt_confirmation(self):
        transport = Transport.objects.create(offre=self.offre)
        self.client.force_login(self.carrier)
        response = self.client.post(reverse('transporteur:transport_evenement', args=[transport.pk]), {
            'statut': Transport.Statut.ARRIVE, 'titre': 'Arrivée à destination', 'lieu': 'Sfax',
            'description': '', 'date_evenement': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        transport.refresh_from_db()
        self.assertEqual(transport.statut, Transport.Statut.ARRIVE)
        self.assertIsNotNone(transport.date_arrivee)
        self.client.force_login(self.pme)
        self.assertEqual(self.client.post(reverse('pme:confirmer_reception', args=[transport.pk])).status_code, 302)
        transport.refresh_from_db()
        self.assertEqual(transport.statut, Transport.Statut.LIVRE)
        self.assertIsNotNone(transport.date_confirmation_reception)
        self.assertEqual(transport.evenements.count(), 2)

    def test_carrier_can_correct_and_delete_own_event(self):
        transport = Transport.objects.create(offre=self.offre)
        self.client.force_login(self.carrier)
        create_url = reverse('transporteur:transport_evenement', args=[transport.pk])
        response = self.client.post(create_url, {
            'statut': Transport.Statut.EN_TRANSIT, 'titre': 'Départ',
            'lieu': 'Tunis', 'description': 'Initial', 'date_evenement':
                timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        event = transport.evenements.exclude(cree_par=None).get()
        edit_url = reverse('transporteur:transport_evenement_edit', args=[transport.pk, event.pk])
        response = self.client.post(edit_url, {
            'statut': Transport.Statut.ARRIVE, 'titre': 'Arrivée',
            'lieu': 'Sfax', 'description': 'Corrigé', 'date_evenement':
                timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        transport.refresh_from_db()
        self.assertEqual(event.titre, 'Arrivée')
        self.assertEqual(transport.statut, Transport.Statut.ARRIVE)
        self.assertIsNotNone(transport.date_arrivee)
        delete_url = reverse(
            'transporteur:transport_evenement_delete', args=[transport.pk, event.pk],
        )
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertFalse(EvenementSuivi.objects.filter(pk=event.pk).exists())

    def test_event_and_transport_operations_are_role_scoped(self):
        transport = Transport.objects.create(offre=self.offre)
        event = EvenementSuivi.objects.create(
            transport=transport, statut=Transport.Statut.EN_TRANSIT,
            titre='Suivi', date_evenement=timezone.now(), cree_par=self.carrier,
        )
        self.client.force_login(self.other_pme)
        self.assertEqual(
            self.client.get(reverse('transporteur:transport_detail', args=[transport.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse(
                'transporteur:transport_evenement_delete', args=[transport.pk, event.pk],
            )).status_code,
            403,
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse('pme:transports_list')).status_code, 302)

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from .models import DemandeTransport, Marchandise


class DemandesTransportTests(TestCase):
    def valid_payload(self, date_depart=None, date_limite=None):
        date_depart = date_depart or date.today() + timedelta(days=1)
        date_limite = date_limite or date_depart + timedelta(days=1)
        return {
            'depart_ville': 'Tunis',
            'depart_adresse': 'Rue des Métiers',
            'date_depart': date_depart.isoformat(),
            'arrivee_ville': 'Sfax',
            'arrivee_adresse': 'Zone industrielle',
            'date_limite': date_limite.isoformat(),
            'destinataire_nom': 'Huiles du Sud',
            'destinataire_contact': 'Ahmed Trabelsi',
            'destinataire_tel': '21698765432',
            'hayon': 'on',
            'consignes': 'Appeler avant livraison',
            'budget': '420.00',
            'modalite_paiement': 'livraison',
            'validite_offres': '48h',
            'marchandises-TOTAL_FORMS': '1',
            'marchandises-INITIAL_FORMS': '0',
            'marchandises-MIN_NUM_FORMS': '1',
            'marchandises-MAX_NUM_FORMS': '15',
            'marchandises-0-description': 'Palettes de bouteilles',
            'marchandises-0-type': 'palettes',
            'marchandises-0-poids': '1850',
            'marchandises-0-volume': '4.8',
            'marchandises-0-fragile': 'on',
        }

    def test_create_published_demand_and_its_goods(self):
        response = self.client.post(reverse('pme:demande_create'), self.valid_payload())

        self.assertRedirects(response, reverse('pme:demandes_list'))
        demande = DemandeTransport.objects.get()
        self.assertEqual(demande.statut, DemandeTransport.Statut.OUVERTE)
        self.assertEqual(demande.depart_ville, 'Tunis')
        self.assertEqual(demande.marchandises.count(), 1)
        self.assertEqual(Marchandise.objects.get().poids, 1850)

        response = self.client.get(reverse('pme:demandes_list'))
        self.assertContains(response, 'Tunis → Sfax')
        self.assertContains(response, 'Huiles du Sud')
        self.assertContains(response, reverse('pme:demande_detail_item', args=[demande.pk]))

    def test_draft_is_saved_with_brouillon_status(self):
        payload = self.valid_payload()
        payload['action'] = 'draft'
        self.client.post(reverse('pme:demande_create'), payload)

        self.assertEqual(DemandeTransport.objects.get().statut, DemandeTransport.Statut.BROUILLON)

    def test_reception_date_before_pickup_is_rejected(self):
        date_depart = date.today() + timedelta(days=2)
        response = self.client.post(
            reverse('pme:demande_create'),
            self.valid_payload(date_depart=date_depart, date_limite=date_depart - timedelta(days=1)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'égale ou postérieure')
        self.assertFalse(DemandeTransport.objects.exists())

    def test_demands_are_scoped_to_anonymous_session(self):
        self.client.post(reverse('pme:demande_create'), self.valid_payload())

        other_client = self.client_class()
        response = other_client.get(reverse('pme:demandes_list'))

        self.assertContains(response, 'Aucune demande pour le moment')

    def test_phone_number_accepts_digits_only(self):
        response = self.client.post(reverse('pme:demande_create'), self.valid_payload())

        self.assertRedirects(response, reverse('pme:demandes_list'))
        self.assertEqual(DemandeTransport.objects.get().destinataire_tel, '21698765432')

    def test_phone_number_rejects_spaces_and_symbols(self):
        payload = self.valid_payload()
        payload['destinataire_tel'] = '+216 98 765 432'
        response = self.client.post(reverse('pme:demande_create'), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'uniquement des chiffres')
        self.assertFalse(DemandeTransport.objects.exists())

    def test_dashboard_uses_demands_from_current_session(self):
        self.client.post(reverse('pme:demande_create'), self.valid_payload())

        response = self.client.get(reverse('pme:dashboard'))

        self.assertContains(response, 'Tunis → Sfax')
        self.assertContains(response, 'Demandes publiées')
        self.assertContains(response, '<strong>1</strong>', html=True)
        self.assertNotContains(response, 'AgroMed Distribution')


class TransporteurDemandesTests(TestCase):
    def create_demand(self, status=DemandeTransport.Statut.OUVERTE, **overrides):
        fields = {
            'statut': status,
            'depart_ville': 'Tunis',
            'depart_adresse': 'Rue des Métiers',
            'date_depart': date.today() + timedelta(days=2),
            'arrivee_ville': 'Sfax',
            'arrivee_adresse': 'Zone industrielle',
            'date_limite': date.today() + timedelta(days=3),
            'destinataire_nom': 'Huiles du Sud',
            'destinataire_contact': 'Contact confidentiel',
            'destinataire_tel': '21698765432',
            'budget': 420,
        }
        fields.update(overrides)
        demande = DemandeTransport.objects.create(**fields)
        Marchandise.objects.create(
            demande=demande,
            description='Palettes huile olive',
            type=Marchandise.Type.PALETTES,
            poids=1850,
            volume=4.8,
            fragile=True,
        )
        return demande

    def test_transporteur_sees_open_demands_and_can_open_details(self):
        demande = self.create_demand()
        self.create_demand(
            status=DemandeTransport.Statut.BROUILLON,
            depart_ville='Nabeul',
        )

        response = self.client.get(reverse('transporteur:demandes'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(demande))
        self.assertContains(response, 'Tunis → Sfax')
        self.assertContains(
            response,
            reverse('transporteur:demande_detail', args=[demande.pk]),
        )
        self.assertNotContains(response, 'Nabeul')

        response = self.client.get(
            reverse('transporteur:demande_detail', args=[demande.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Palettes huile olive')
        self.assertContains(response, 'Rue des Métiers')
        self.assertNotContains(response, '21698765432')
        self.assertNotContains(response, 'Contact confidentiel')

    def test_transporteur_can_search_open_demands_by_city_or_goods(self):
        self.create_demand()
        self.create_demand(
            depart_ville='Nabeul',
            arrivee_ville='Bizerte',
        )

        response = self.client.get(reverse('transporteur:demandes'), {'q': 'Tunis'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tunis → Sfax')
        self.assertNotContains(response, 'Nabeul → Bizerte')

    def test_transporteur_cannot_open_draft_detail(self):
        demande = self.create_demand(status=DemandeTransport.Statut.BROUILLON)

        response = self.client.get(
            reverse('transporteur:demande_detail', args=[demande.pk]),
        )

        self.assertEqual(response.status_code, 404)

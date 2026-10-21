from datetime import date, timedelta

from django.contrib.auth import get_user_model
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
    def setUp(self):
        self.pme = get_user_model().objects.create_user(email='pme@example.com', role='PME')
        transporteur = get_user_model().objects.create_user(email='transporteur@example.com', role='transporteur')
        self.client.force_login(transporteur)

    def create_demand(self, status=DemandeTransport.Statut.OUVERTE, **overrides):
        fields = {
            'created_by': self.pme,
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


class PmeDemandeCrudTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.pme = user_model.objects.create_user(
            email='pme-crud@example.com',
            password='safe-test-password',
            role='PME',
        )
        self.other_pme = user_model.objects.create_user(
            email='other-pme@example.com',
            password='safe-test-password',
            role='PME',
        )
        self.client.force_login(self.pme)

    def create_demand(self, owner=None, **overrides):
        fields = {
            'created_by': owner or self.pme,
            'statut': DemandeTransport.Statut.OUVERTE,
            'depart_ville': 'Tunis',
            'depart_adresse': 'Rue des Métiers',
            'date_depart': date.today() + timedelta(days=2),
            'arrivee_ville': 'Sfax',
            'arrivee_adresse': 'Zone industrielle',
            'date_limite': date.today() + timedelta(days=3),
            'destinataire_nom': 'Huiles du Sud',
            'destinataire_contact': 'Ahmed Trabelsi',
            'destinataire_tel': '21698765432',
        }
        fields.update(overrides)
        demande = DemandeTransport.objects.create(**fields)
        Marchandise.objects.create(
            demande=demande,
            description='Palette huile',
            type=Marchandise.Type.PALETTES,
            poids=120,
        )
        return demande

    def test_pme_can_edit_its_demand_and_goods(self):
        demande = self.create_demand()
        payload = DemandesTransportTests().valid_payload()
        payload.update({
            'depart_ville': 'Nabeul',
            'marchandises-0-description': 'Cartons huile',
            'marchandises-0-poids': '250',
            'marchandises-0-id': str(demande.marchandises.get().pk),
            'marchandises-TOTAL_FORMS': '1',
            'marchandises-INITIAL_FORMS': '1',
        })

        response = self.client.post(
            reverse('pme:demande_update', args=[demande.pk]),
            payload,
        )

        self.assertRedirects(
            response,
            reverse('pme:demande_detail_item', args=[demande.pk]),
        )
        demande.refresh_from_db()
        self.assertEqual(demande.depart_ville, 'Nabeul')
        self.assertEqual(demande.marchandises.get().description, 'Cartons huile')
        self.assertEqual(demande.marchandises.get().poids, 250)

    def test_pme_can_delete_its_demand_and_goods(self):
        demande = self.create_demand()

        response = self.client.post(reverse('pme:demande_delete', args=[demande.pk]))

        self.assertRedirects(response, reverse('pme:demandes_list'))
        self.assertFalse(DemandeTransport.objects.filter(pk=demande.pk).exists())
        self.assertFalse(Marchandise.objects.exists())

    def test_pme_cannot_view_edit_or_delete_another_pmes_demand(self):
        demande = self.create_demand(owner=self.other_pme)

        for route in (
            reverse('pme:demande_detail_item', args=[demande.pk]),
            reverse('pme:demande_update', args=[demande.pk]),
            reverse('pme:demande_delete', args=[demande.pk]),
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 404)

        response = self.client.post(reverse('pme:demande_delete', args=[demande.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(DemandeTransport.objects.filter(pk=demande.pk).exists())

    def test_admin_can_hide_and_restore_demand(self):
        admin = get_user_model().objects.create_superuser(
            email='admin@example.com',
            password='safe-test-password',
            full_name='Administrateur',
        )
        demande = self.create_demand()
        self.client.force_login(admin)
        changelist = reverse('admin:demandes_demandetransport_changelist')

        response = self.client.post(changelist, {
            'action': 'hide_demands',
            '_selected_action': [demande.pk],
            'index': 0,
        })
        self.assertRedirects(response, changelist)
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeTransport.Statut.MASQUEE)

        transporteur = get_user_model().objects.create_user(
            email='transporteur-admin-check@example.com',
            password='safe-test-password',
            role='transporteur',
        )
        self.client.force_login(transporteur)
        response = self.client.get(reverse('transporteur:demandes'))
        self.assertNotContains(response, str(demande))
        self.client.force_login(self.pme)
        response = self.client.get(reverse('pme:demandes_list'))
        self.assertContains(response, str(demande))

        self.client.force_login(admin)
        self.client.post(changelist, {
            'action': 'publish_demands',
            '_selected_action': [demande.pk],
            'index': 0,
        })
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeTransport.Statut.OUVERTE)

        delete_url = reverse('admin:demandes_demandetransport_delete', args=[demande.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.client.post(delete_url, {'post': 'yes'})
        self.assertFalse(DemandeTransport.objects.filter(pk=demande.pk).exists())

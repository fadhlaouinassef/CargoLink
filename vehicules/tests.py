from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from authentification.models import User

from .models import Disponibilite, Vehicule


class VehiculeModelTests(TestCase):
    def setUp(self):
        self.transporteur = User.objects.create_user(
            email='transporteur@example.com',
            password='Strong-password-872!',
            full_name='Transporteur Test',
            role=User.Role.TRANSPORTEUR,
        )

    def vehicle_data(self, **overrides):
        data = {
            'transporteur': self.transporteur,
            'immatriculation': '123 TUN 4567',
            'marque': 'Iveco',
            'modele': 'Daily',
            'annee': timezone.now().year,
            'type_vehicule': Vehicule.TypeVehicule.CAMIONNETTE,
            'capacite_poids_kg': Decimal('1200.00'),
            'capacite_volume_m3': Decimal('8.50'),
        }
        data.update(overrides)
        return data

    def create_vehicle(self, **overrides):
        vehicle = Vehicule(**self.vehicle_data(**overrides))
        vehicle.full_clean()
        vehicle.save()
        return vehicle

    def test_vehicle_str_and_normalizes_registration(self):
        vehicle = self.create_vehicle(immatriculation=' ab-123 ')
        self.assertEqual(vehicle.immatriculation, 'AB-123')
        self.assertEqual(str(vehicle), 'AB-123 — Iveco Daily')

    def test_only_transporters_can_own_vehicles(self):
        user = User.objects.create_user(
            email='pme@example.com',
            password='Strong-password-872!',
            full_name='PME Test',
            role=User.Role.PME,
        )
        with self.assertRaises(ValidationError):
            Vehicule(**self.vehicle_data(transporteur=user)).full_clean()

    def test_vehicle_rejects_invalid_year_and_capacities(self):
        with self.assertRaises(ValidationError):
            Vehicule(**self.vehicle_data(annee=1979)).full_clean()
        with self.assertRaises(ValidationError):
            Vehicule(**self.vehicle_data(capacite_poids_kg=0)).full_clean()
        with self.assertRaises(ValidationError):
            Vehicule(**self.vehicle_data(capacite_volume_m3=0)).full_clean()

    def test_photo_rejects_oversized_file(self):
        oversized = SimpleUploadedFile('truck.jpg', b'x' * (2 * 1024 * 1024 + 1), content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            Vehicule(**self.vehicle_data(photo=oversized)).full_clean()

    def test_reserved_availability_protects_vehicle_deletion(self):
        vehicle = self.create_vehicle()
        Disponibilite.objects.create(
            vehicule=vehicle,
            date_debut=timezone.now() + timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=2),
            zone_depart='Tunis',
            zone_arrivee='Sousse',
            statut=Disponibilite.Statut.RESERVE,
        )
        with self.assertRaises(ValidationError):
            vehicle.delete()


class DisponibiliteModelTests(VehiculeModelTests):
    def availability_data(self, **overrides):
        now = timezone.now()
        data = {
            'vehicule': self.create_vehicle(immatriculation='AV-001'),
            'date_debut': now + timedelta(days=1),
            'date_fin': now + timedelta(days=2),
            'zone_depart': 'Tunis',
            'zone_arrivee': 'Sfax',
            'statut': Disponibilite.Statut.DISPONIBLE,
        }
        data.update(overrides)
        return data

    def test_availability_str(self):
        availability = Disponibilite(**self.availability_data())
        availability.full_clean()
        self.assertEqual(str(availability), 'AV-001 — Tunis → Sfax')

    def test_end_must_be_after_start_and_start_cannot_be_past(self):
        data = self.availability_data()
        with self.assertRaises(ValidationError):
            Disponibilite(**{**data, 'date_fin': data['date_debut']}).full_clean()
        with self.assertRaises(ValidationError):
            Disponibilite(**{**data, 'date_debut': timezone.now() - timedelta(minutes=1)}).full_clean()

    def test_maintenance_and_disabled_vehicles_cannot_receive_availability(self):
        vehicle = self.create_vehicle(
            immatriculation='MAINT-001',
            statut=Vehicule.Statut.EN_MAINTENANCE,
        )
        with self.assertRaises(ValidationError):
            Disponibilite(**self.availability_data(vehicule=vehicle)).full_clean()

    def test_active_availabilities_cannot_overlap(self):
        data = self.availability_data()
        first = Disponibilite(**data)
        first.full_clean()
        first.save()
        with self.assertRaises(ValidationError):
            Disponibilite(**{
                **data,
                'date_debut': data['date_debut'] + timedelta(hours=1),
            }).full_clean()

    def test_indisponible_period_can_overlap(self):
        data = self.availability_data()
        first = Disponibilite.objects.create(**data)
        second = Disponibilite(**{
            **data,
            'date_debut': data['date_debut'] + timedelta(hours=1),
            'statut': Disponibilite.Statut.INDISPONIBLE,
        })
        second.full_clean()
        self.assertEqual(first.statut, Disponibilite.Statut.DISPONIBLE)


class TransporteurVehicleViewTests(TestCase):
    def setUp(self):
        self.transporteur = User.objects.create_user(
            email='owner@example.com',
            password='Strong-password-872!',
            full_name='Propriétaire Test',
            role=User.Role.TRANSPORTEUR,
        )
        self.other_transporteur = User.objects.create_user(
            email='other@example.com',
            password='Strong-password-872!',
            full_name='Autre Transporteur',
            role=User.Role.TRANSPORTEUR,
        )

    def vehicle_payload(self, registration='VIEW-001'):
        return {
            'immatriculation': registration,
            'marque': 'Renault',
            'modele': 'Master',
            'annee': timezone.now().year,
            'type_vehicule': Vehicule.TypeVehicule.CAMIONNETTE,
            'capacite_poids_kg': '1500',
            'capacite_volume_m3': '12',
            'statut': Vehicule.Statut.ACTIF,
        }

    def test_transporteur_can_create_vehicle_and_availability(self):
        self.client.force_login(self.transporteur)
        response = self.client.post(
            reverse('transporteur:vehicule_create'),
            self.vehicle_payload(),
        )
        self.assertRedirects(response, reverse('transporteur:vehicules'))
        vehicle = Vehicule.objects.get(immatriculation='VIEW-001')
        now = timezone.now()
        response = self.client.post(reverse('transporteur:disponibilite_create'), {
            'vehicule': vehicle.pk,
            'date_debut': (now + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'date_fin': (now + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
            'zone_depart': 'Tunis',
            'zone_arrivee': 'Sfax',
            'statut': Disponibilite.Statut.DISPONIBLE,
            'commentaire': 'Créneau de test',
        })
        self.assertRedirects(response, reverse('transporteur:vehicules'))
        self.assertEqual(vehicle.disponibilites.count(), 1)

    def test_transporteur_cannot_access_another_transporters_vehicle(self):
        vehicle = Vehicule.objects.create(**{
            **self.vehicle_payload('OTHER-001'),
            'transporteur': self.other_transporteur,
        })
        self.client.force_login(self.transporteur)
        response = self.client.get(reverse('transporteur:vehicule_update', args=[vehicle.pk]))
        self.assertEqual(response.status_code, 404)

    def test_transporteur_can_update_vehicle_and_availability(self):
        self.client.force_login(self.transporteur)
        vehicle = Vehicule.objects.create(
            transporteur=self.transporteur,
            **self.vehicle_payload('UPDATE-001'),
        )
        response = self.client.get(
            reverse('transporteur:vehicule_update', args=[vehicle.pk]),
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('transporteur:vehicule_update', args=[vehicle.pk]),
            self.vehicle_payload('UPDATED-001') | {'marque': 'Volvo'},
        )
        self.assertRedirects(response, reverse('transporteur:vehicules'))
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.immatriculation, 'UPDATED-001')
        self.assertEqual(vehicle.marque, 'Volvo')

        now = timezone.now()
        availability = Disponibilite.objects.create(
            vehicule=vehicle,
            date_debut=now + timedelta(days=3),
            date_fin=now + timedelta(days=4),
            zone_depart='Tunis',
            zone_arrivee='Sfax',
        )
        response = self.client.get(
            reverse('transporteur:disponibilite_update', args=[availability.pk]),
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('transporteur:disponibilite_update', args=[availability.pk]),
            {
                'vehicule': vehicle.pk,
                'date_debut': (now + timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),
                'date_fin': (now + timedelta(days=6)).strftime('%Y-%m-%dT%H:%M'),
                'zone_depart': 'Sousse',
                'zone_arrivee': 'Bizerte',
                'statut': Disponibilite.Statut.DISPONIBLE,
                'commentaire': 'Période modifiée',
            },
        )
        self.assertRedirects(response, reverse('transporteur:vehicules'))
        availability.refresh_from_db()
        self.assertEqual(availability.zone_depart, 'Sousse')
        self.assertEqual(availability.zone_arrivee, 'Bizerte')
        self.assertEqual(
            self.client.get(
                reverse('transporteur:disponibilite_detail', args=[availability.pk]),
            ).status_code,
            200,
        )

    def test_delete_forms_require_post_and_include_confirmation(self):
        self.client.force_login(self.transporteur)
        vehicle = Vehicule.objects.create(
            transporteur=self.transporteur,
            **self.vehicle_payload('DELETE-001'),
        )
        response = self.client.get(reverse('transporteur:vehicules'))
        self.assertContains(response, 'data-confirm-delete="Supprimer ce véhicule ? Cette action est irréversible."')
        self.assertEqual(
            self.client.get(
                reverse('transporteur:vehicule_delete', args=[vehicle.pk]),
            ).status_code,
            200,
        )


class AdminVehicleViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='vehicle-admin@example.com',
            password='Strong-password-872!',
            full_name='Admin Véhicules',
            role=User.Role.ADMIN,
        )
        self.transporteur = User.objects.create_user(
            email='vehicle-owner@example.com',
            password='Strong-password-872!',
            full_name='Transporteur Propriétaire',
            role=User.Role.TRANSPORTEUR,
        )
        self.vehicle = Vehicule.objects.create(
            transporteur=self.transporteur,
            immatriculation='ADMIN-001',
            marque='Iveco',
            modele='Daily',
            annee=2024,
            type_vehicule=Vehicule.TypeVehicule.CAMION,
            capacite_poids_kg=3000,
            capacite_volume_m3=18,
        )

    def test_admin_supervision_list_and_detail_are_styled_pages(self):
        self.client.force_login(self.admin)
        list_response = self.client.get(reverse('authentification:admin_vehicles'))
        detail_response = self.client.get(
            reverse('authentification:admin_vehicle_detail', args=[self.vehicle.pk]),
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'Supervisez la flotte')
        self.assertContains(list_response, 'ADMIN-001')
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Historique des disponibilités')

    def test_non_admin_cannot_access_supervision(self):
        self.client.force_login(self.transporteur)
        response = self.client.get(reverse('authentification:admin_vehicles'))
        self.assertEqual(response.status_code, 404)

    def test_admin_can_create_update_and_delete_vehicle(self):
        self.client.force_login(self.admin)
        create_response = self.client.post(
            reverse('authentification:admin_vehicle_create'),
            {
                'transporteur': self.transporteur.pk,
                'immatriculation': 'ADMIN-002',
                'marque': 'Mercedes',
                'modele': 'Actros',
                'annee': 2025,
                'type_vehicule': Vehicule.TypeVehicule.CAMION,
                'capacite_poids_kg': '5000',
                'capacite_volume_m3': '25',
                'statut': Vehicule.Statut.ACTIF,
            },
        )
        self.assertRedirects(create_response, reverse('authentification:admin_vehicles'))
        created = Vehicule.objects.get(immatriculation='ADMIN-002')
        self.assertEqual(created.transporteur, self.transporteur)
        update_response = self.client.post(
            reverse('authentification:admin_vehicle_update', args=[created.pk]),
            {
                'transporteur': self.transporteur.pk,
                'immatriculation': 'ADMIN-002B',
                'marque': 'Mercedes',
                'modele': 'Actros',
                'annee': 2025,
                'type_vehicule': Vehicule.TypeVehicule.CAMION,
                'capacite_poids_kg': '5500',
                'capacite_volume_m3': '25',
                'statut': Vehicule.Statut.EN_MAINTENANCE,
            },
        )
        self.assertRedirects(update_response, reverse('authentification:admin_vehicles'))
        created.refresh_from_db()
        self.assertEqual(created.statut, Vehicule.Statut.EN_MAINTENANCE)
        delete_response = self.client.post(
            reverse('authentification:admin_vehicle_delete', args=[created.pk]),
        )
        self.assertRedirects(delete_response, reverse('authentification:admin_vehicles'))
        self.assertFalse(Vehicule.objects.filter(pk=created.pk).exists())

    def test_admin_can_update_availability(self):
        self.client.force_login(self.admin)
        now = timezone.now()
        availability = Disponibilite.objects.create(
            vehicule=self.vehicle,
            date_debut=now + timedelta(days=2),
            date_fin=now + timedelta(days=3),
            zone_depart='Tunis',
            zone_arrivee='Sfax',
        )
        response = self.client.get(
            reverse('authentification:admin_availability_update', args=[availability.pk]),
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('authentification:admin_availability_update', args=[availability.pk]),
            {
                'vehicule': self.vehicle.pk,
                'date_debut': (now + timedelta(days=4)).strftime('%Y-%m-%dT%H:%M'),
                'date_fin': (now + timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),
                'zone_depart': 'Sousse',
                'zone_arrivee': 'Bizerte',
                'statut': Disponibilite.Statut.DISPONIBLE,
                'commentaire': '',
            },
        )
        self.assertRedirects(response, reverse('authentification:admin_vehicles'))
        availability.refresh_from_db()
        self.assertEqual(availability.zone_depart, 'Sousse')
        self.assertEqual(
            self.client.get(
                reverse('authentification:admin_availability_detail', args=[availability.pk]),
            ).status_code,
            200,
        )

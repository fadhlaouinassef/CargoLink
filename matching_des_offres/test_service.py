"""Tests unitaires pour l'intégration Django du modèle de matching."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from avis_reclamations.models import Avis
from demandes.models import DemandeTransport, Marchandise
from gestion_trajets_offres.models import OffreTransport, Trajet
from matching_des_offres.services import (
    evaluate_and_rank_offres,
    extract_matching_row,
    get_carrier_reputation,
    get_matching_bundle,
)
from vehicules.models import Vehicule

User = get_user_model()


class MatchingDjangoIntegrationTests(TestCase):
    def setUp(self):
        self.pme = User.objects.create_user(
            email="pme@test.tn",
            password="password123",
            role=User.Role.PME,
            first_name="PME",
            last_name="Test",
        )
        self.carrier_1 = User.objects.create_user(
            email="carrier1@test.tn",
            password="password123",
            role=User.Role.TRANSPORTEUR,
            first_name="Mohamed",
            last_name="Triki",
        )
        self.carrier_2 = User.objects.create_user(
            email="carrier2@test.tn",
            password="password123",
            role=User.Role.TRANSPORTEUR,
            first_name="Ali",
            last_name="Ben Salah",
        )

        # Véhicule actif pour carrier 1
        self.vehicule_1 = Vehicule.objects.create(
            transporteur=self.carrier_1,
            immatriculation="123-TN-456",
            marque="Isuzu",
            modele="NPR",
            annee=2022,
            type_vehicule=Vehicule.TypeVehicule.CAMIONNETTE,
            capacite_poids_kg=Decimal("1500.00"),
            capacite_volume_m3=Decimal("12.00"),
            statut=Vehicule.Statut.ACTIF,
        )

        # Avis pour carrier 1
        self.demande_anc = DemandeTransport.objects.create(
            created_by=self.pme,
            depart_ville="Tunis",
            depart_adresse="Zone 1",
            date_depart=date.today() - timedelta(days=20),
            arrivee_ville="Sousse",
            arrivee_adresse="Zone 2",
            date_limite=date.today() - timedelta(days=18),
            destinataire_nom="Client Ancien",
            destinataire_contact="Contact",
            destinataire_tel="20111222",
        )
        Avis.objects.create(
            auteur=self.pme,
            transporteur=self.carrier_1,
            demande=self.demande_anc,
            note=5,
            commentaire="Excellent transporteur, très ponctuel.",
            statut=Avis.Statut.PUBLIE,
        )

        # Demande actuelle
        self.demande = DemandeTransport.objects.create(
            created_by=self.pme,
            depart_ville="Tunis",
            depart_adresse="La Charguia",
            date_depart=date.today() + timedelta(days=2),
            arrivee_ville="Sousse",
            arrivee_adresse="Kantaoui",
            date_limite=date.today() + timedelta(days=5),
            destinataire_nom="Destinataire",
            destinataire_contact="Contact",
            destinataire_tel="20123456",
            budget=Decimal("200.00"),
        )
        Marchandise.objects.create(
            demande=self.demande,
            description="Palette de pièces",
            type=Marchandise.Type.PALETTES,
            poids=Decimal("400.00"),
            volume=Decimal("3.00"),
        )

        # Trajet compatible pour carrier 1
        self.trajet_1 = Trajet.objects.create(
            transporteur=self.carrier_1,
            depart_ville="Tunis",
            arrivee_ville="Sousse",
            date_depart=self.demande.date_depart + timedelta(days=1),
            vehicule=self.vehicule_1.immatriculation,
            capacite_kg=Decimal("1000.00"),
            volume_m3=Decimal("8.00"),
            statut=Trajet.Statut.PUBLIE,
        )
        self.offre_1 = OffreTransport.objects.create(
            transporteur=self.carrier_1,
            demande=self.demande,
            trajet=self.trajet_1,
            prix=Decimal("180.00"),
        )

        # Trajet avec capacité insuffisante pour carrier 2
        self.trajet_2 = Trajet.objects.create(
            transporteur=self.carrier_2,
            depart_ville="Tunis",
            arrivee_ville="Sousse",
            date_depart=self.demande.date_depart + timedelta(days=1),
            vehicule="INCONNU-999",
            capacite_kg=Decimal("200.00"),  # Moins que les 400kg demandés !
            volume_m3=Decimal("1.00"),
            statut=Trajet.Statut.PUBLIE,
        )
        self.offre_2 = OffreTransport.objects.create(
            transporteur=self.carrier_2,
            demande=self.demande,
            trajet=self.trajet_2,
            prix=Decimal("150.00"),
        )

    def test_reputation_carrier(self):
        note, total = get_carrier_reputation(self.carrier_1)
        self.assertEqual(note, 5.0)
        self.assertEqual(total, 1)

        note2, total2 = get_carrier_reputation(self.carrier_2)
        self.assertEqual(note2, 0.0)
        self.assertEqual(total2, 0)

    def test_extract_matching_row(self):
        row = extract_matching_row(self.demande, self.offre_1)
        self.assertEqual(row["poids_kg"], 400.0)
        self.assertEqual(row["volume_m3"], 3.0)
        self.assertEqual(row["prix"], 180.0)
        self.assertEqual(row["budget"], 200.0)
        self.assertTrue(row["trajet_compatible"])
        self.assertTrue(row["creneau_compatible"])
        self.assertTrue(row["vehicule_disponible"])
        self.assertEqual(row["note_transporteur"], 5.0)
        self.assertEqual(row["nombre_avis"], 1)

    def test_evaluate_and_rank_offres(self):
        result = evaluate_and_rank_offres(self.demande)
        
        # Offre 1 doit être admissible et classée
        self.assertEqual(len(result["classement"]), 1)
        first = result["classement"][0]
        self.assertEqual(first.offre_id, self.offre_1.pk)
        self.assertGreater(first.score, 0)
        self.assertFalse(first.rejetee)

        # Offre 2 doit être rejetée pour capacité insuffisante
        self.assertEqual(len(result["offres_exclues"]), 1)
        rejected = result["offres_exclues"][0]
        self.assertEqual(rejected.offre_id, self.offre_2.pk)
        self.assertTrue(rejected.rejetee)
        self.assertTrue(any("Capacité en poids insuffisante" in r for r in rejected.motifs_rejet))

    def test_model_loaded_without_training(self):
        bundle = get_matching_bundle()
        self.assertIn("pipeline", bundle)
        self.assertIn("threshold", bundle)
        self.assertGreater(bundle["threshold"], 0)

"""Tests de l'endpoint qui fournit le classement des offres au popup de la PME."""
import ast
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock, skipUnless

import numpy as np
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from authentification.models import User
from demandes.models import DemandeTransport, Marchandise
from gestion_trajets_offres.models import OffreTransport, Trajet
from matching_des_offres import services
from vehicules.models import Vehicule

MOT_DE_PASSE = 'Cargo-Strong-872!'


class FauxPipeline:
    """Remplace le modèle entraîné : plus le prix est bas par rapport au budget, plus le score est haut."""

    def predict_proba(self, frame):
        score = (1 - frame['ratio_prix_budget'] / 2).clip(0, 1).to_numpy()
        return np.column_stack([1 - score, score])


def creer_utilisateur(email, role, nom):
    return User.objects.create_user(email, MOT_DE_PASSE, full_name=nom, role=role)


class BaseEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pme = creer_utilisateur('pme@example.com', User.Role.PME, 'AgroMed Distribution')
        cls.autre_pme = creer_utilisateur('pme2@example.com', User.Role.PME, 'Autre PME')
        cls.transporteurs = [
            creer_utilisateur(f't{i}@example.com', User.Role.TRANSPORTEUR, nom)
            for i, nom in enumerate(['Mohamed Triki', 'Ali Ben Salah', 'Sami Gharbi'], start=1)
        ]
        cls.vehicule = Vehicule.objects.create(
            transporteur=cls.transporteurs[0], immatriculation='123-TN-456', marque='Isuzu', modele='NPR', annee=2022,
            type_vehicule=Vehicule.TypeVehicule.CAMIONNETTE, capacite_poids_kg=Decimal('1500'),
            capacite_volume_m3=Decimal('12'), statut=Vehicule.Statut.ACTIF,
        )
        aujourdhui = timezone.now().date()
        cls.depart = timezone.now() + timedelta(days=3)
        cls.demande = DemandeTransport.objects.create(
            created_by=cls.pme, depart_ville='Tunis', depart_adresse='La Charguia',
            date_depart=aujourdhui + timedelta(days=2), arrivee_ville='Sousse', arrivee_adresse='Kantaoui',
            date_limite=aujourdhui + timedelta(days=5), destinataire_nom='Destinataire',
            destinataire_contact='Contact', destinataire_tel='20123456', budget=Decimal('200.00'),
        )
        Marchandise.objects.create(
            demande=cls.demande, description='Palette de pièces', type=Marchandise.Type.PALETTES,
            poids=Decimal('400'), volume=Decimal('3'),
        )

    def setUp(self):
        # Modèle simulé : les tests ne dépendent ni du fichier entraîné ni de son contenu.
        patcher = mock.patch.object(services, '_LOADED_BUNDLE', {'pipeline': FauxPipeline(), 'threshold': 0.5})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse('pme:offres_classees', args=[self.demande.pk])
        self.client.force_login(self.pme)

    def creer_offre(self, transporteur, prix, capacite_kg='1000', volume='8', vehicule='123-TN-456',
                    demande=None, statut=None):
        trajet = Trajet.objects.create(
            transporteur=transporteur, depart_ville='Tunis', arrivee_ville='Sousse', date_depart=self.depart,
            vehicule=vehicule, capacite_kg=Decimal(capacite_kg), volume_m3=Decimal(volume), statut=Trajet.Statut.PUBLIE,
        )
        extra = {'statut': statut} if statut else {}
        return OffreTransport.objects.create(
            transporteur=transporteur, demande=demande or self.demande, trajet=trajet, prix=Decimal(str(prix)), **extra,
        )

    def charger(self, url=None):
        response = self.client.get(url or self.url)
        return response, response.json()


class AccesTests(BaseEndpointTests):
    def test_proprietaire_autorise(self):
        response, donnees = self.charger()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(donnees['demande']['id'], self.demande.pk)

    def test_anonyme_refuse_en_json(self):
        self.client.logout()
        response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (401, 'non_authentifie'))

    def test_les_autres_roles_sont_refuses(self):
        for utilisateur in (self.transporteurs[0],):
            self.client.force_login(utilisateur)
            response, donnees = self.charger()
            self.assertEqual((response.status_code, donnees['statut']), (403, 'acces_refuse'))

    def test_une_autre_pme_ne_voit_rien_et_ne_sait_pas_si_la_demande_existe(self):
        self.client.force_login(self.autre_pme)
        autre, corps_autre = self.charger()
        inexistante, corps_inexistant = self.charger(reverse('pme:offres_classees', args=[999999]))
        self.assertEqual((autre.status_code, inexistante.status_code), (404, 404))
        self.assertEqual(corps_autre, corps_inexistant)

    def test_seule_la_lecture_est_permise(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_reponse_non_mise_en_cache(self):
        self.assertIn('no-store', self.client.get(self.url)['Cache-Control'])

    def test_la_vue_n_importe_pas_les_bibliotheques_du_modele_au_chargement(self):
        """Sans scikit-learn, le site doit continuer de démarrer : seuls ces imports tardifs sont concernés."""
        arbre = ast.parse(Path(__file__).with_name('views.py').read_text(encoding='utf-8'))
        importes = []
        for noeud in arbre.body:
            if isinstance(noeud, ast.Import):
                importes += [alias.name for alias in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                importes += [f'{noeud.module}.{alias.name}' for alias in noeud.names]
        interdits = ('services', 'joblib', 'sklearn', 'pandas', 'numpy')
        self.assertEqual([nom for nom in importes if any(mot in nom for mot in interdits)], [])


class ClassementTests(BaseEndpointTests):
    def test_offres_classees_exclues_et_criteres(self):
        bonne = self.creer_offre(self.transporteurs[0], 180)                       # véhicule référencé
        moins_chere = self.creer_offre(self.transporteurs[2], 160, vehicule='INCONNU-1')  # véhicule hors catalogue
        trop_petite = self.creer_offre(self.transporteurs[1], 150, capacite_kg='200')

        response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (200, 'ok'))

        # Classement : rang, score décroissant, prix.
        self.assertEqual([o['offre_id'] for o in donnees['offres']], [moins_chere.pk, bonne.pk])
        self.assertEqual([o['rang'] for o in donnees['offres']], [1, 2])
        self.assertEqual([o['score'] for o in donnees['offres']], [60.0, 55.0])
        self.assertEqual([o['prix'] for o in donnees['offres']], [160.0, 180.0])
        self.assertTrue(all(o['pertinent_predit'] for o in donnees['offres']))
        self.assertEqual(donnees['offres'][0]['capacites'], {'poids_kg': 1000.0, 'volume_m3': 8.0})
        self.assertEqual(donnees['demande']['date_depart'], self.demande.date_depart.isoformat())
        self.assertEqual(donnees['demande']['date_limite'], self.demande.date_limite.isoformat())

        # Motifs d'exclusion.
        self.assertEqual([o['offre_id'] for o in donnees['exclues']], [trop_petite.pk])
        self.assertIn('Capacité en poids insuffisante', donnees['exclues'][0]['motifs'])
        self.assertEqual(donnees['non_evaluables'], [])

        # Critères vérifiés, avec leurs limites.
        premier, second = donnees['offres']
        self.assertEqual([c['code'] for c in second['criteres']],
                         ['trajet', 'creneau', 'capacites', 'vehicule', 'marchandise', 'budget'])
        self.assertTrue(all(c['verifie'] is True for c in second['criteres']))
        self.assertEqual(second['type_vehicule'], 'camionnette')
        vehicule = next(c for c in premier['criteres'] if c['code'] == 'vehicule')
        self.assertIsNone(vehicule['verifie'])
        self.assertIn('non référencé', vehicule['detail'])
        self.assertIsNone(premier['type_vehicule'])  # le type par défaut du service n'est pas affiché

        # Identité, réputation et lien d'acceptation pour le popup.
        self.assertEqual(second['transporteur'], {'id': self.transporteurs[0].pk, 'nom': 'Mohamed Triki', 'note': 0.0, 'nombre_avis': 0})
        self.assertEqual(second['vehicule_reference'], '123-TN-456')
        self.assertEqual(second['details_vehicule'], {'description': 'Isuzu NPR', 'type': 'Camionnette'})
        self.assertEqual(second['trajet']['date_depart'], bonne.trajet.date_depart.isoformat())
        self.assertEqual(second['url_accepter'], reverse('pme:accepter_offre', args=[self.demande.pk, bonne.pk]))
        self.assertEqual(donnees['modele'], {'seuil_pertinence': 0.5})

    def test_le_score_est_presente_comme_un_indicateur_de_classement(self):
        self.creer_offre(self.transporteurs[0], 180)
        _, donnees = self.charger()
        self.assertIn('indicateur de classement', donnees['avertissement'])
        self.assertIn("pas une probabilité de réussite", donnees['avertissement'])
        self.assertNotIn('probabilite', donnees['offres'][0])

    def test_offres_refusees_ignorees_et_offre_acceptee_incluse(self):
        refusee = self.creer_offre(self.transporteurs[1], 150, statut=OffreTransport.Statut.REFUSEE)
        acceptee = self.creer_offre(self.transporteurs[0], 180, statut=OffreTransport.Statut.ACCEPTEE)
        _, donnees = self.charger()
        identifiants = [o['offre_id'] for liste in (donnees['offres'], donnees['exclues'], donnees['non_evaluables']) for o in liste]
        self.assertEqual(identifiants, [acceptee.pk])
        self.assertEqual(donnees['offres'][0]['statut_offre'], 'acceptee')
        self.assertIsNone(donnees['offres'][0]['url_accepter'])
        self.assertNotIn(refusee.pk, identifiants)

    def test_pas_de_lien_d_acceptation_si_la_demande_n_est_plus_ouverte(self):
        self.creer_offre(self.transporteurs[0], 180)
        DemandeTransport.objects.filter(pk=self.demande.pk).update(statut=DemandeTransport.Statut.MASQUEE)
        _, donnees = self.charger()
        self.assertIsNone(donnees['offres'][0]['url_accepter'])

    def test_depassement_du_budget_est_signale_sans_exclure(self):
        self.creer_offre(self.transporteurs[0], 250)
        _, donnees = self.charger()
        offre = donnees['offres'][0]
        self.assertTrue(offre['depasse_budget'])
        budget = next(c for c in offre['criteres'] if c['code'] == 'budget')
        self.assertIs(budget['verifie'], False)
        self.assertIn('200', budget['detail'])

    def test_budget_absent(self):
        DemandeTransport.objects.filter(pk=self.demande.pk).update(budget=None)
        self.creer_offre(self.transporteurs[0], 180)
        _, donnees = self.charger()
        budget = next(c for c in donnees['offres'][0]['criteres'] if c['code'] == 'budget')
        self.assertIsNone(budget['verifie'])
        self.assertIsNone(donnees['demande']['budget'])


class SituationsParticulieresTests(BaseEndpointTests):
    def test_aucune_offre_sans_charger_le_modele(self):
        with mock.patch.object(services, 'get_matching_bundle', side_effect=AssertionError('modèle chargé')):
            response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (200, 'aucune_offre'))
        self.assertEqual((donnees['offres'], donnees['exclues'], donnees['non_evaluables']), ([], [], []))

    def test_aucune_offre_admissible(self):
        trop_petite = self.creer_offre(self.transporteurs[1], 150, capacite_kg='200')
        response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (200, 'aucune_offre_admissible'))
        self.assertEqual(donnees['offres'], [])
        self.assertEqual([o['offre_id'] for o in donnees['exclues']], [trop_petite.pk])

    def test_donnees_insuffisantes_volume_non_renseigne(self):
        Marchandise.objects.filter(demande=self.demande).update(volume=None)
        offre = self.creer_offre(self.transporteurs[0], 180)
        response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (200, 'donnees_insuffisantes'))
        self.assertEqual(donnees['offres'], [])   # aucune valeur inventée, aucune offre classée
        self.assertEqual(donnees['exclues'], [])  # ni jugée incompatible
        self.assertEqual([o['offre_id'] for o in donnees['non_evaluables']], [offre.pk])
        self.assertIn('Volume des marchandises non renseigné', donnees['non_evaluables'][0]['motifs'][0])

    def test_donnees_insuffisantes_demande_sans_marchandise(self):
        Marchandise.objects.filter(demande=self.demande).delete()
        self.creer_offre(self.transporteurs[0], 180)
        _, donnees = self.charger()
        self.assertEqual(donnees['statut'], 'donnees_insuffisantes')
        self.assertEqual(len(donnees['non_evaluables']), 1)

    def verifier_modele_indisponible(self):
        with self.assertLogs('matching_des_offres.views', level='ERROR'):
            response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (503, 'modele_indisponible'))
        self.assertEqual(donnees['offres'], [])
        corps = response.content.decode()
        for detail_technique in ('Traceback', 'FileNotFoundError', 'joblib', 'artifacts', 'sklearn'):
            self.assertNotIn(detail_technique, corps)  # aucun détail interne n'est exposé

    def test_fichier_du_modele_absent(self):
        self.creer_offre(self.transporteurs[0], 180)
        with tempfile.TemporaryDirectory() as dossier, \
                mock.patch.object(services, '_LOADED_BUNDLE', None), \
                mock.patch.object(services, 'DEFAULT_MODEL_PATH', Path(dossier) / 'absent.joblib'):
            self.verifier_modele_indisponible()

    def test_fichier_du_modele_illisible(self):
        self.creer_offre(self.transporteurs[0], 180)
        with tempfile.TemporaryDirectory() as dossier:
            corrompu = Path(dossier) / 'model.joblib'
            corrompu.write_bytes(b'ceci n est pas un modele')
            with mock.patch.object(services, '_LOADED_BUNDLE', None), \
                    mock.patch.object(services, 'DEFAULT_MODEL_PATH', corrompu):
                self.verifier_modele_indisponible()

    def test_bibliotheques_du_modele_manquantes(self):
        self.creer_offre(self.transporteurs[0], 180)
        with mock.patch.object(services, 'get_matching_bundle', side_effect=ModuleNotFoundError("No module named 'sklearn'")):
            self.verifier_modele_indisponible()


@skipUnless(services.DEFAULT_MODEL_PATH.exists(), "Modèle non entraîné : lancer `generate` puis `train` (voir modele.md).")
class AvecLeVraiModeleTests(BaseEndpointTests):
    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # retire le faux modèle : le vrai fichier entraîné est chargé
        services._LOADED_BUNDLE = None
        self.addCleanup(setattr, services, '_LOADED_BUNDLE', None)
        self.url = reverse('pme:offres_classees', args=[self.demande.pk])
        self.client.force_login(self.pme)

    def test_classement_avec_le_modele_entraine(self):
        self.creer_offre(self.transporteurs[0], 180)
        self.creer_offre(self.transporteurs[2], 160)
        response, donnees = self.charger()
        self.assertEqual((response.status_code, donnees['statut']), (200, 'ok'))
        scores = [o['score'] for o in donnees['offres']]
        self.assertEqual(len(scores), 2)
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0 <= s <= 100 for s in scores))
        self.assertEqual([o['rang'] for o in donnees['offres']], [1, 2])
        self.assertIsInstance(donnees['offres'][0]['pertinent_predit'], bool)

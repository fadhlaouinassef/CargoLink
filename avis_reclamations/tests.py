import io
import json
import os
import urllib.error
from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from authentification.models import User
from demandes.models import DemandeTransport

from .forms import evaluer_langage, seuil_gravite
from .models import Avis, Reclamation

MOT_DE_PASSE = 'Cargo-Strong-872!'


def creer_utilisateur(email, role, nom, **extra):
    return User.objects.create_user(email, MOT_DE_PASSE, full_name=nom, role=role, **extra)


def creer_demande(createur, destinataire_nom='Huiles du Sud', **extra):
    return DemandeTransport.objects.create(
        created_by=createur,
        depart_ville='Tunis', depart_adresse='Zone industrielle', date_depart=date(2026, 10, 1),
        arrivee_ville='Sfax', arrivee_adresse='Route de Gabès', date_limite=date(2026, 10, 5),
        destinataire_nom=destinataire_nom, destinataire_contact='Responsable', destinataire_tel='20123456',
        **extra,
    )


class BaseTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patcher = mock.patch('avis_reclamations.forms.evaluer_langage', return_value={'gravite': 0.0, 'mots': []})
        cls.evaluation = patcher.start()
        cls.addClassCleanup(patcher.stop)

    @classmethod
    def setUpTestData(cls):
        cls.pme = creer_utilisateur('pme@example.com', User.Role.PME, 'AgroMed Distribution')
        cls.autre_pme = creer_utilisateur('pme2@example.com', User.Role.PME, 'Autre PME')
        cls.transporteur = creer_utilisateur('trans@example.com', User.Role.TRANSPORTEUR, 'Express Sahel')
        cls.destinataire = creer_utilisateur('dest@example.com', User.Role.DESTINATAIRE, 'Huiles du Sud')
        cls.admin = creer_utilisateur('admin@example.com', User.Role.ADMIN, 'Admin CargoLink', is_staff=True)
        cls.demande = creer_demande(cls.pme)

    def connecter(self, utilisateur):
        self.client.force_login(utilisateur)


class AccesTests(BaseTestCase):
    def test_pages_protegees_redirigent_les_anonymes(self):
        urls = [
            reverse('pme:avis_list'), reverse('pme:avis_create'),
            reverse('pme:reclamation_list'), reverse('pme:reclamation_create'),
            reverse('destinataire:reclamation'), reverse('destinataire:reclamation_list'),
            reverse('transporteur:avis'),
            reverse('avis_admin:reclamation_list'), reverse('avis_admin:avis_list'),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('authentification:login'), response['Location'])

    def test_un_mauvais_role_est_refuse(self):
        interdits = [
            (self.transporteur, 'pme:avis_create'),
            (self.destinataire, 'pme:avis_create'),
            (self.destinataire, 'pme:reclamation_create'),
            (self.pme, 'destinataire:reclamation'),
            (self.pme, 'transporteur:avis'),
            (self.pme, 'avis_admin:reclamation_list'),
            (self.transporteur, 'avis_admin:avis_list'),
        ]
        for utilisateur, nom_url in interdits:
            with self.subTest(utilisateur=utilisateur.role, url=nom_url):
                self.connecter(utilisateur)
                self.assertEqual(self.client.get(reverse(nom_url)).status_code, 403)

    def test_chaque_role_ouvre_ses_pages(self):
        ouvertes = [
            (self.pme, ['pme:avis_list', 'pme:avis_create', 'pme:reclamation_list', 'pme:reclamation_create']),
            (self.destinataire, ['destinataire:reclamation', 'destinataire:reclamation_list']),
            (self.transporteur, ['transporteur:avis']),
            (self.admin, ['avis_admin:reclamation_list', 'avis_admin:avis_list']),
        ]
        for utilisateur, noms in ouvertes:
            self.connecter(utilisateur)
            for nom_url in noms:
                with self.subTest(utilisateur=utilisateur.role, url=nom_url):
                    self.assertEqual(self.client.get(reverse(nom_url)).status_code, 200)


class AvisTests(BaseTestCase):
    def setUp(self):
        self.url = reverse('pme:avis_create')
        self.donnees = {
            'demande': self.demande.pk,
            'transporteur': self.transporteur.pk,
            'note': 5,
            'commentaire': 'Transporteur ponctuel et très sérieux, merci.',
        }
        self.connecter(self.pme)

    def test_creation_valide(self):
        response = self.client.post(self.url, self.donnees)
        self.assertRedirects(response, reverse('pme:avis_list'))
        avis = Avis.objects.get()
        self.assertEqual((avis.auteur, avis.transporteur, avis.demande, avis.note), (self.pme, self.transporteur, self.demande, 5))
        self.assertTrue(avis.est_publie)

    def test_champs_invalides_sont_refuses_avec_message(self):
        cas = {
            'demande': ({'demande': ''}, 'Choisissez la demande concernée.'),
            'transporteur': ({'transporteur': ''}, 'Choisissez le transporteur à évaluer.'),
            'note': ({'note': ''}, 'Attribuez une note de 1 à 5 étoiles.'),
            'note hors limites': ({'note': 6}, 'La note doit être comprise entre 1 et 5.'),
            'commentaire court': ({'commentaire': 'Trop bref'}, 'au moins 10 caractères'),
            'commentaire vide': ({'commentaire': '   '}, 'obligatoire'),
            'commentaire long': ({'commentaire': 'x' * 1001}, 'au plus 1000 caractères'),
        }
        for nom, (changement, message) in cas.items():
            with self.subTest(nom):
                response = self.client.post(self.url, {**self.donnees, **changement})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertContains(response, 'Le formulaire contient')
                self.assertFalse(Avis.objects.exists())

    def test_on_ne_peut_evaluer_que_ses_demandes_publiees_et_des_transporteurs_actifs(self):
        brouillon = creer_demande(self.pme, statut=DemandeTransport.Statut.BROUILLON)
        d_autrui = creer_demande(self.autre_pme)
        inactif = creer_utilisateur('off@example.com', User.Role.TRANSPORTEUR, 'Inactif', is_active=False)
        for nom, changement in {
            'brouillon': {'demande': brouillon.pk},
            'demande d’un autre': {'demande': d_autrui.pk},
            'transporteur inactif': {'transporteur': inactif.pk},
            'compte non transporteur': {'transporteur': self.destinataire.pk},
        }.items():
            with self.subTest(nom):
                response = self.client.post(self.url, {**self.donnees, **changement})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Avis.objects.exists())

    def test_une_demande_ne_peut_etre_evaluee_qu_une_fois(self):
        self.client.post(self.url, self.donnees)
        response = self.client.post(self.url, {**self.donnees, 'note': 1})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'déjà évaluée')
        self.assertEqual(Avis.objects.count(), 1)
        self.assertEqual(Avis.objects.get().note, 5)

    def test_formulaire_vide_sans_demande_disponible(self):
        self.connecter(self.autre_pme)
        response = self.client.get(self.url)
        self.assertContains(response, 'Aucune demande à évaluer')
        self.assertNotContains(response, 'name="commentaire"')

    def test_liste_et_preselection(self):
        Avis.objects.create(auteur=self.pme, transporteur=self.transporteur, demande=self.demande, note=4, commentaire='Très bien dans l’ensemble.')
        self.assertContains(self.client.get(reverse('pme:avis_list')), 'Express Sahel')
        autre = creer_demande(self.pme)
        response = self.client.get(self.url, {'demande': autre.pk})
        self.assertEqual(response.context['form'].initial['demande'], str(autre.pk))

    def test_csrf_obligatoire(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.pme)
        self.assertEqual(client.post(self.url, self.donnees).status_code, 403)


class ProfilTransporteurEtModerationTests(BaseTestCase):
    def setUp(self):
        self.avis_5 = Avis.objects.create(auteur=self.pme, transporteur=self.transporteur, demande=self.demande, note=5, commentaire='Excellent travail, merci !')
        demande2 = creer_demande(self.autre_pme)
        self.avis_3 = Avis.objects.create(auteur=self.autre_pme, transporteur=self.transporteur, demande=demande2, note=3, commentaire='Correct sans plus.')

    def test_statistiques_ne_comptent_que_les_avis_publies(self):
        self.assertEqual(Avis.objects.publies().filter(transporteur=self.transporteur).stats()['moyenne'], 4)
        self.avis_3.statut = Avis.Statut.MASQUE
        self.avis_3.save()
        stats = Avis.objects.publies().filter(transporteur=self.transporteur).stats()
        self.assertEqual((stats['moyenne'], stats['total'], stats['arrondie']), (5, 1, 5))

    def test_page_transporteur_affiche_ses_avis_publies(self):
        self.avis_3.statut = Avis.Statut.MASQUE
        self.avis_3.save()
        self.connecter(self.transporteur)
        response = self.client.get(reverse('transporteur:avis'))
        self.assertContains(response, 'Excellent travail')
        self.assertNotContains(response, 'Correct sans plus')
        self.assertEqual(response.context['stats']['total'], 1)
        self.assertNotContains(response, 'Données fictives')

    def test_moderation_masquer_exige_un_motif(self):
        self.connecter(self.admin)
        url = reverse('avis_admin:avis_detail', args=[self.avis_5.pk])
        for motif in ['', 'abc']:
            with self.subTest(motif=motif):
                response = self.client.post(url, {'action': 'masquer', 'motif': motif})
                self.assertEqual(response.status_code, 200)
                self.avis_5.refresh_from_db()
                self.assertTrue(self.avis_5.est_publie)

    def test_moderation_masquer_puis_republier(self):
        self.connecter(self.admin)
        url = reverse('avis_admin:avis_detail', args=[self.avis_5.pk])
        self.assertRedirects(self.client.post(url, {'action': 'masquer', 'motif': 'Propos injurieux'}), url)
        self.avis_5.refresh_from_db()
        self.assertEqual((self.avis_5.statut, self.avis_5.motif_moderation), (Avis.Statut.MASQUE, 'Propos injurieux'))
        self.assertRedirects(self.client.post(url, {'action': 'publier'}), url)
        self.avis_5.refresh_from_db()
        self.assertEqual((self.avis_5.statut, self.avis_5.motif_moderation), (Avis.Statut.PUBLIE, ''))

    def test_action_inconnue_refusee(self):
        self.connecter(self.admin)
        response = self.client.post(reverse('avis_admin:avis_detail', args=[self.avis_5.pk]), {'action': 'supprimer'})
        self.assertEqual(response.status_code, 200)

    def test_liste_admin_filtres(self):
        self.connecter(self.admin)
        url = reverse('avis_admin:avis_list')
        self.assertEqual(len(self.client.get(url).context['page']), 2)
        self.assertEqual(len(self.client.get(url, {'note': 3}).context['page']), 1)
        self.assertEqual(len(self.client.get(url, {'q': 'Excellent'}).context['page']), 1)
        self.assertEqual(len(self.client.get(url, {'statut': 'masque'}).context['page']), 0)
        self.assertEqual(len(self.client.get(url, {'note': 'abc', 'statut': 'x'}).context['page']), 2)


class ReclamationTests(BaseTestCase):
    def setUp(self):
        self.donnees = {
            'demande': self.demande.pk,
            'transporteur': self.transporteur.pk,
            'motif': 'avarie',
            'description': 'Deux palettes sont arrivées renversées et endommagées.',
            'montant_prejudice': '650.50',
        }

    def deposer(self, utilisateur, nom_url, donnees=None):
        self.connecter(utilisateur)
        return self.client.post(reverse(nom_url), donnees or self.donnees)

    def test_depot_par_une_pme(self):
        response = self.deposer(self.pme, 'pme:reclamation_create')
        reclamation = Reclamation.objects.get()
        self.assertRedirects(response, reverse('pme:reclamation_detail', args=[reclamation.pk]))
        self.assertEqual((reclamation.auteur, reclamation.statut, str(reclamation.montant_prejudice)), (self.pme, 'ouverte', '650.50'))
        self.assertRegex(reclamation.reference, r'^REC-\d{4}-\d{4}$')

    def test_depot_par_un_destinataire_sur_sa_demande(self):
        response = self.deposer(self.destinataire, 'destinataire:reclamation')
        reclamation = Reclamation.objects.get()
        self.assertRedirects(response, reverse('destinataire:reclamation_detail', args=[reclamation.pk]))
        self.assertEqual(reclamation.auteur, self.destinataire)

    def test_destinataire_ne_voit_pas_les_demandes_des_autres(self):
        autre = creer_demande(self.pme, destinataire_nom='Quelqu’un d’autre')
        response = self.deposer(self.destinataire, 'destinataire:reclamation', {**self.donnees, 'demande': autre.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pas disponible')
        self.assertFalse(Reclamation.objects.exists())

    def test_champs_invalides_sont_refuses_avec_message(self):
        cas = {
            'demande': ({'demande': ''}, 'Choisissez la demande concernée.'),
            'motif': ({'motif': ''}, 'Choisissez le motif de la réclamation.'),
            'motif inconnu': ({'motif': 'zzz'}, 'motif n’est pas valide'),
            'description courte': ({'description': 'Trop court'}, 'au moins 20 caractères'),
            'description longue': ({'description': 'x' * 2001}, 'au plus 2000 caractères'),
            'montant négatif': ({'montant_prejudice': '-5'}, 'ne peut pas être négatif'),
            'montant énorme': ({'montant_prejudice': '2000000'}, 'ne peut pas dépasser'),
            'montant texte': ({'montant_prejudice': 'beaucoup'}, 'montant valide'),
            'trop de décimales': ({'montant_prejudice': '10.123'}, '2 chiffres'),
        }
        for nom, (changement, message) in cas.items():
            with self.subTest(nom):
                response = self.deposer(self.pme, 'pme:reclamation_create', {**self.donnees, **changement})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertFalse(Reclamation.objects.exists())

    def test_transporteur_et_montant_sont_facultatifs(self):
        donnees = {**self.donnees, 'transporteur': '', 'montant_prejudice': ''}
        self.deposer(self.pme, 'pme:reclamation_create', donnees)
        reclamation = Reclamation.objects.get()
        self.assertIsNone(reclamation.transporteur)
        self.assertIsNone(reclamation.montant_prejudice)

    def test_pas_de_doublon_tant_que_le_dossier_est_ouvert(self):
        self.deposer(self.pme, 'pme:reclamation_create')
        response = self.deposer(self.pme, 'pme:reclamation_create')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'déjà en cours')
        Reclamation.objects.update(statut=Reclamation.Statut.RESOLUE)
        self.deposer(self.pme, 'pme:reclamation_create')
        self.assertEqual(Reclamation.objects.count(), 2)

    def test_un_auteur_ne_voit_que_ses_reclamations(self):
        self.deposer(self.pme, 'pme:reclamation_create')
        reclamation = Reclamation.objects.get()
        url = reverse('pme:reclamation_detail', args=[reclamation.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.connecter(self.autre_pme)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(len(self.client.get(reverse('pme:reclamation_list')).context['page']), 0)

    def test_le_transporteur_voit_les_reclamations_qui_le_visent(self):
        self.deposer(self.pme, 'pme:reclamation_create')
        self.connecter(self.transporteur)
        response = self.client.get(reverse('transporteur:avis'))
        self.assertEqual(response.context['reclamations_total'], 1)
        self.assertContains(response, Reclamation.objects.get().reference)


class FakeReponseApi:
    """Réponse simulée de l'API Groq (aucun appel réseau dans les tests)."""

    def __init__(self, gravite=None, mots=(), contenu=None, brut=None):
        if brut is None:
            contenu = contenu if contenu is not None else json.dumps({'gravite': gravite, 'mots': list(mots)})
            brut = json.dumps({'choices': [{'message': {'content': contenu}}]}).encode('utf-8')
        self.corps = brut

    def __enter__(self):
        return io.BytesIO(self.corps)

    def __exit__(self, *args):
        return False


class EvaluerLangageTests(TestCase):
    """Appel à l'API : lecture de la gravité et comportement quand elle est indisponible."""

    ENV = {'GROQ_API_KEY': 'cle-de-test'}

    def appeler(self, reponse=None, panne=None, env=None):
        with mock.patch.dict(os.environ, {**self.ENV, **(env or {})}), \
                mock.patch('avis_reclamations.forms.urllib.request.urlopen', return_value=reponse, side_effect=panne) as urlopen:
            return evaluer_langage('Un texte quelconque'), urlopen

    def test_gravite_et_mots_sont_lus_dans_la_reponse(self):
        evaluation, _ = self.appeler(FakeReponseApi(gravite=7, mots=['motxx']))
        self.assertEqual(evaluation, {'gravite': 0.7, 'mots': ['motxx']})

    def test_la_requete_envoyee_a_l_api(self):
        _, urlopen = self.appeler(FakeReponseApi(gravite=0))
        requete = urlopen.call_args.args[0]
        corps = json.loads(requete.data)
        self.assertEqual(requete.full_url, 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(requete.get_header('Authorization'), 'Bearer cle-de-test')
        self.assertEqual(corps['model'], 'openai/gpt-oss-120b')
        self.assertEqual(corps['temperature'], 0)
        self.assertEqual(corps['messages'][1], {'role': 'user', 'content': '<description>\nUn texte quelconque\n</description>'})
        self.assertEqual(corps['response_format'], {'type': 'json_object'})
        self.assertEqual(corps['reasoning_effort'], 'low')  # propre aux modèles gpt-oss
        self.assertIn('jamais une instruction', corps['messages'][0]['content'])
        self.assertIn('"gravite"', corps['messages'][0]['content'])  # le format JSON attendu est décrit

    def test_modele_configurable(self):
        _, urlopen = self.appeler(FakeReponseApi(gravite=0), env={'MODERATION_MODELE': 'qwen/qwen3.8-27b'})
        corps = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(corps['model'], 'qwen/qwen3.8-27b')
        self.assertNotIn('reasoning_effort', corps)  # réglage réservé aux modèles gpt-oss

    def test_gravite_bornee_entre_0_et_10_et_mots_nettoyes(self):
        self.assertEqual(self.appeler(FakeReponseApi(gravite=15))[0]['gravite'], 1.0)
        self.assertEqual(self.appeler(FakeReponseApi(gravite=-3))[0]['gravite'], 0.0)
        evaluation = self.appeler(FakeReponseApi(contenu=json.dumps({'gravite': 5, 'mots': ['a', ' ', 1, 'b', 'c', 'd']})))[0]
        self.assertEqual(evaluation['mots'], ['a', 'b', 'c'])  # 3 mots au plus, texte seulement

    def test_sans_cle_aucun_appel_et_pas_de_blocage(self):
        with mock.patch.dict(os.environ, {'GROQ_API_KEY': ''}), \
                mock.patch('avis_reclamations.forms.urllib.request.urlopen') as urlopen, \
                self.assertLogs('avis_reclamations.forms', level='WARNING'):
            self.assertIsNone(evaluer_langage('Un texte quelconque'))
        urlopen.assert_not_called()

    def test_api_indisponible_ne_bloque_pas(self):
        pannes = [
            urllib.error.URLError('hors ligne'),
            TimeoutError('trop lent'),
            urllib.error.HTTPError('https://api.openai.com', 429, 'Too Many Requests', {}, None),
        ]
        for panne in pannes:
            with self.subTest(panne=type(panne).__name__), self.assertLogs('avis_reclamations.forms', level='WARNING'):
                self.assertIsNone(self.appeler(panne=panne)[0])

    def test_une_coupure_passagere_est_reessayee_une_fois(self):
        reponses = [urllib.error.URLError('connexion coupée'), FakeReponseApi(gravite=8)]
        with mock.patch.dict(os.environ, self.ENV), \
                mock.patch('avis_reclamations.forms.urllib.request.urlopen', side_effect=reponses) as urlopen, \
                self.assertLogs('avis_reclamations.forms', level='WARNING'):
            self.assertEqual(evaluer_langage('Un texte quelconque')['gravite'], 0.8)
        self.assertEqual(urlopen.call_count, 2)

    def test_deux_echecs_de_suite_abandonnent_sans_bloquer(self):
        with mock.patch.dict(os.environ, self.ENV), \
                mock.patch('avis_reclamations.forms.urllib.request.urlopen', side_effect=urllib.error.URLError('hors ligne')) as urlopen, \
                self.assertLogs('avis_reclamations.forms', level='WARNING'):
            self.assertIsNone(evaluer_langage('Un texte quelconque'))
        self.assertEqual(urlopen.call_count, 2)

    def test_reponse_invalide_ne_bloque_pas(self):
        reponses = [
            FakeReponseApi(brut=b'pas du json'),
            FakeReponseApi(brut=b'{}'),
            FakeReponseApi(brut=b'{"choices": []}'),
            FakeReponseApi(brut=json.dumps({'choices': [{'message': {'content': None}}]}).encode()),  # refus du modèle
            FakeReponseApi(contenu='pas du json'),
            FakeReponseApi(contenu='{"mots": []}'),
            FakeReponseApi(contenu='{"gravite": "beaucoup", "mots": []}'),
        ]
        for reponse in reponses:
            with self.subTest(corps=reponse.corps), self.assertLogs('avis_reclamations.forms', level='WARNING'):
                self.assertIsNone(self.appeler(reponse)[0])

    def test_seuil_configurable_et_borne(self):
        for valeur, attendu in [('0.5', 0.5), ('2', 1.0), ('-1', 0.0), ('abc', 0.4)]:
            with self.subTest(valeur=valeur), mock.patch.dict(os.environ, {'MODERATION_SEUIL': valeur}):
                self.assertEqual(seuil_gravite(), attendu)
        environnement = {cle: valeur for cle, valeur in os.environ.items() if cle != 'MODERATION_SEUIL'}
        with mock.patch.dict(os.environ, environnement, clear=True):
            self.assertEqual(seuil_gravite(), 0.4)


class BlocageParGraviteTests(BaseTestCase):
    """La description d'une réclamation est refusée quand la gravité évaluée atteint le seuil."""

    def setUp(self):
        self.evaluation.reset_mock()
        self.evaluation.return_value = {'gravite': 0.0, 'mots': []}
        self.url = reverse('pme:reclamation_create')
        self.donnees = {
            'demande': self.demande.pk,
            'motif': 'avarie',
            'description': 'Deux palettes sont arrivées renversées et endommagées.',
        }
        self.connecter(self.pme)

    def deposer(self, gravite, mots=(), description=None):
        self.evaluation.return_value = None if gravite is None else {'gravite': gravite, 'mots': list(mots)}
        return self.client.post(self.url, {**self.donnees, 'description': description or self.donnees['description']})

    def test_texte_acceptable_accepte(self):
        for gravite in (0.0, 0.1, 0.3):  # critique ou ton familier : jusqu'à 3 sur 10
            with self.subTest(gravite=gravite):
                self.assertEqual(self.deposer(gravite).status_code, 302)
                Reclamation.objects.update(statut=Reclamation.Statut.RESOLUE)  # un seul dossier ouvert par demande
        self.assertEqual(Reclamation.objects.count(), 3)

    def test_au_seuil_ou_au_dessus_refuse_avec_le_niveau(self):
        texte = 'Un texte jugé inapproprié par le modèle.'
        for gravite, niveau in [(0.4, 'moyenne'), (0.6, 'moyenne'), (0.7, 'élevée'), (0.8, 'élevée'), (0.9, 'très élevée'), (1.0, 'très élevée')]:
            with self.subTest(gravite=gravite):
                response = self.deposer(gravite, description=texte)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'gravité {niveau} : {round(gravite * 10)}/10')
                self.assertIn('description', response.context['form'].errors)
                self.assertContains(response, texte)  # le texte saisi est conservé
                self.assertFalse(Reclamation.objects.exists())

    def test_les_mots_releves_sont_masques(self):
        response = self.deposer(0.5, mots=['aaaa', 'bbbbbb'])
        self.assertContains(response, '« a*** »')
        self.assertContains(response, '« b***** »')
        self.assertNotContains(response, '« aaaa »')

    def test_les_mots_trop_courts_ne_sont_pas_affiches(self):
        response = self.deposer(0.7, mots=['tu', 'es', 'méchant'])
        message = ' '.join(response.context['form'].errors['description'])
        self.assertIn('« m****** »', message)
        self.assertNotIn('« t* »', message)
        self.assertNotIn('« e* »', message)

    def test_message_sans_mot_quand_le_modele_n_en_cite_aucun(self):
        message = ' '.join(self.deposer(0.8).context['form'].errors['description'])
        self.assertIn('gravité élevée : 8/10)', message)
        self.assertNotIn('«', message)

    def test_seuil_modifiable_dans_env(self):
        with mock.patch.dict(os.environ, {'MODERATION_SEUIL': '0.8'}):
            self.assertEqual(self.deposer(0.7).status_code, 302)
        with mock.patch.dict(os.environ, {'MODERATION_SEUIL': '0.2'}):
            self.assertEqual(self.deposer(0.3).status_code, 200)

    def test_api_indisponible_ne_bloque_pas_le_depot(self):
        self.assertEqual(self.deposer(None).status_code, 302)
        self.assertEqual(Reclamation.objects.count(), 1)

    def test_texte_trop_court_ne_declenche_pas_d_appel(self):
        response = self.deposer(0.0, description='Trop court')
        self.assertEqual(response.status_code, 200)
        self.evaluation.assert_not_called()

    def test_le_texte_envoye_a_l_api_est_la_description(self):
        self.deposer(0.0)
        self.evaluation.assert_called_once_with(self.donnees['description'])

    def test_les_avis_ne_passent_pas_par_l_api(self):
        reponse = self.client.post(reverse('pme:avis_create'), {
            'demande': self.demande.pk, 'transporteur': self.transporteur.pk, 'note': 2,
            'commentaire': 'Service décevant, chauffeur désagréable et livraison tardive.',
        })
        self.assertEqual(reponse.status_code, 302)
        self.evaluation.assert_not_called()


class ModificationSuppressionReclamationTests(BaseTestCase):
    """L'auteur modifie ou supprime sa réclamation tant qu'elle est « Ouverte » ; ensuite c'est verrouillé."""

    def setUp(self):
        self.evaluation.reset_mock()
        self.evaluation.return_value = {'gravite': 0.0, 'mots': []}
        self.reclamation = Reclamation.objects.create(
            auteur=self.pme, demande=self.demande, transporteur=self.transporteur,
            motif=Reclamation.Motif.RETARD, description='Livraison arrivée avec deux jours de retard.',
        )
        self.url_detail = reverse('pme:reclamation_detail', args=[self.reclamation.pk])
        self.url_update = reverse('pme:reclamation_update', args=[self.reclamation.pk])
        self.url_delete = reverse('pme:reclamation_delete', args=[self.reclamation.pk])
        self.donnees = {
            'demande': self.demande.pk, 'transporteur': '', 'motif': 'avarie',
            'description': 'Deux palettes sont arrivées renversées et endommagées.', 'montant_prejudice': '120.00',
        }
        self.connecter(self.pme)

    def passer_au_statut(self, statut):
        Reclamation.objects.filter(pk=self.reclamation.pk).update(statut=statut)

    def test_modifier_une_reclamation_ouverte(self):
        response = self.client.get(self.url_update)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].fields['demande'].disabled)
        self.assertContains(response, 'Livraison arrivée avec deux jours de retard.')
        self.assertRedirects(self.client.post(self.url_update, self.donnees), self.url_detail)
        self.reclamation.refresh_from_db()
        self.assertEqual(
            (self.reclamation.motif, self.reclamation.description, str(self.reclamation.montant_prejudice), self.reclamation.transporteur),
            ('avarie', 'Deux palettes sont arrivées renversées et endommagées.', '120.00', None),
        )
        self.assertEqual((self.reclamation.statut, self.reclamation.demande), ('ouverte', self.demande))

    def test_la_demande_ne_peut_pas_etre_changee(self):
        autre = creer_demande(self.pme)
        self.client.post(self.url_update, {**self.donnees, 'demande': autre.pk})
        self.reclamation.refresh_from_db()
        self.assertEqual(self.reclamation.demande, self.demande)

    def test_la_modification_controle_la_saisie(self):
        for changement, message in [
            ({'description': 'Trop court'}, 'au moins 20 caractères'),
            ({'motif': ''}, 'Choisissez le motif'),
            ({'montant_prejudice': '-5'}, 'ne peut pas être négatif'),
        ]:
            with self.subTest(changement=changement):
                response = self.client.post(self.url_update, {**self.donnees, **changement})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.reclamation.refresh_from_db()
                self.assertEqual(self.reclamation.motif, 'retard')

    def test_la_modification_passe_aussi_par_le_filtre_de_langage(self):
        self.evaluation.return_value = {'gravite': 0.8, 'mots': []}
        response = self.client.post(self.url_update, self.donnees)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'langage inapproprié')
        self.reclamation.refresh_from_db()
        self.assertEqual(self.reclamation.motif, 'retard')

    def test_supprimer_une_reclamation_ouverte_avec_confirmation(self):
        response = self.client.get(self.url_delete)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Supprimer définitivement')
        self.assertTrue(Reclamation.objects.filter(pk=self.reclamation.pk).exists())  # un simple GET ne supprime rien
        self.assertRedirects(self.client.post(self.url_delete), reverse('pme:reclamation_list'))
        self.assertFalse(Reclamation.objects.filter(pk=self.reclamation.pk).exists())

    def test_dossier_pris_en_charge_ou_cloture_est_verrouille(self):
        for statut in (Reclamation.Statut.EN_COURS, Reclamation.Statut.RESOLUE, Reclamation.Statut.REJETEE):
            self.passer_au_statut(statut)
            for nom, url, donnees in [('modifier', self.url_update, self.donnees), ('supprimer', self.url_delete, {})]:
                with self.subTest(statut=statut, action=nom):
                    for reponse in (self.client.get(url), self.client.post(url, donnees)):
                        self.assertRedirects(reponse, self.url_detail)
                    self.assertContains(self.client.get(self.url_detail), 'ne peut plus être modifié')
                    self.reclamation.refresh_from_db()
                    self.assertEqual((self.reclamation.motif, self.reclamation.statut), ('retard', statut))
                    self.assertTrue(Reclamation.objects.filter(pk=self.reclamation.pk).exists())

    def test_les_boutons_ne_sont_proposes_que_si_le_dossier_est_ouvert(self):
        self.assertContains(self.client.get(self.url_detail), self.url_update)
        self.assertContains(self.client.get(self.url_detail), self.url_delete)
        self.passer_au_statut(Reclamation.Statut.EN_COURS)
        detail = self.client.get(self.url_detail)
        self.assertNotContains(detail, self.url_update)
        self.assertNotContains(detail, self.url_delete)

    def test_l_administrateur_prend_le_dossier_pendant_que_l_auteur_modifie(self):
        # La page s'est ouverte alors que le dossier était ouvert, puis l'administrateur l'a pris en charge.
        with mock.patch.object(Reclamation, 'est_modifiable', new_callable=mock.PropertyMock, return_value=True):
            self.passer_au_statut(Reclamation.Statut.EN_COURS)
            self.assertRedirects(self.client.post(self.url_update, self.donnees), self.url_detail)
            self.assertRedirects(self.client.post(self.url_delete), self.url_detail)
        self.reclamation.refresh_from_db()
        self.assertEqual((self.reclamation.motif, self.reclamation.statut), ('retard', 'en_cours'))

    def test_un_autre_utilisateur_ne_peut_ni_modifier_ni_supprimer(self):
        self.connecter(self.autre_pme)
        for url in (self.url_update, self.url_delete):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.donnees).status_code, 404)
        self.reclamation.refresh_from_db()
        self.assertEqual(self.reclamation.motif, 'retard')

    def test_un_mauvais_role_est_refuse(self):
        self.connecter(self.destinataire)
        for url in (self.url_update, self.url_delete):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_un_destinataire_modifie_et_supprime_sa_reclamation(self):
        reclamation = Reclamation.objects.create(
            auteur=self.destinataire, demande=self.demande,
            motif=Reclamation.Motif.AVARIE, description='Deux palettes sont arrivées abîmées au quai.',
        )
        self.connecter(self.destinataire)
        detail = reverse('destinataire:reclamation_detail', args=[reclamation.pk])
        response = self.client.post(
            reverse('destinataire:reclamation_update', args=[reclamation.pk]),
            {**self.donnees, 'motif': 'manquant', 'description': 'Une palette manque sur les quatre annoncées.'},
        )
        self.assertRedirects(response, detail)
        reclamation.refresh_from_db()
        self.assertEqual(reclamation.motif, 'manquant')
        self.assertRedirects(
            self.client.post(reverse('destinataire:reclamation_delete', args=[reclamation.pk])),
            reverse('destinataire:reclamation_list'),
        )
        self.assertFalse(Reclamation.objects.filter(pk=reclamation.pk).exists())


class TraitementReclamationTests(BaseTestCase):
    def setUp(self):
        self.reclamation = Reclamation.objects.create(
            auteur=self.pme, demande=self.demande, transporteur=self.transporteur,
            motif=Reclamation.Motif.RETARD, description='Livraison arrivée avec deux jours de retard.',
        )
        self.url = reverse('avis_admin:reclamation_detail', args=[self.reclamation.pk])
        self.connecter(self.admin)

    def test_modele_transitions_et_reference(self):
        self.assertEqual([v for v, _ in self.reclamation.statuts_suivants()], ['en_cours', 'resolue', 'rejetee'])
        self.assertFalse(self.reclamation.est_close)
        self.reclamation.statut = Reclamation.Statut.EN_COURS
        self.assertEqual([v for v, _ in self.reclamation.statuts_suivants()], ['resolue', 'rejetee'])
        self.reclamation.statut = Reclamation.Statut.REJETEE
        self.assertTrue(self.reclamation.est_close)
        self.assertEqual(self.reclamation.statuts_suivants(), [])

    def test_prise_en_charge_puis_resolution(self):
        self.assertRedirects(self.client.post(self.url, {'statut': 'en_cours', 'reponse': ''}), self.url)
        self.reclamation.refresh_from_db()
        self.assertEqual((self.reclamation.statut, self.reclamation.traitee_par), ('en_cours', self.admin))

        self.client.post(self.url, {'statut': 'resolue', 'reponse': 'Avoir de 80 TND crédité sur votre compte.'})
        self.reclamation.refresh_from_db()
        self.assertEqual(self.reclamation.statut, 'resolue')
        self.assertEqual(self.reclamation.reponse_admin, 'Avoir de 80 TND crédité sur votre compte.')
        self.assertIsNotNone(self.reclamation.traitee_le)

    def test_cloturer_exige_une_reponse(self):
        for statut in ['resolue', 'rejetee']:
            with self.subTest(statut=statut):
                response = self.client.post(self.url, {'statut': statut, 'reponse': ''})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'réponse est obligatoire')
                self.reclamation.refresh_from_db()
                self.assertEqual(self.reclamation.statut, 'ouverte')

    def test_reponse_trop_courte_ou_decision_inconnue_refusees(self):
        for donnees in [{'statut': 'resolue', 'reponse': 'ok'}, {'statut': 'ouverte', 'reponse': ''}, {'statut': 'zzz', 'reponse': ''}, {}]:
            with self.subTest(donnees=donnees):
                self.assertEqual(self.client.post(self.url, donnees).status_code, 200)
                self.reclamation.refresh_from_db()
                self.assertEqual(self.reclamation.statut, 'ouverte')

    def test_dossier_cloture_non_modifiable(self):
        Reclamation.objects.update(statut=Reclamation.Statut.REJETEE, reponse_admin='Aucune preuve fournie.')
        response = self.client.post(self.url, {'statut': 'en_cours', 'reponse': ''})
        self.assertRedirects(response, self.url)
        self.reclamation.refresh_from_db()
        self.assertEqual(self.reclamation.statut, 'rejetee')
        self.assertNotContains(self.client.get(self.url), 'Enregistrer la décision')

    def test_l_auteur_voit_la_reponse(self):
        self.client.post(self.url, {'statut': 'rejetee', 'reponse': 'Aucune preuve fournie dans le dossier.'})
        self.connecter(self.pme)
        response = self.client.get(reverse('pme:reclamation_detail', args=[self.reclamation.pk]))
        self.assertContains(response, 'Aucune preuve fournie dans le dossier.')
        self.assertContains(response, 'Rejetée')

    def test_liste_admin_filtres_et_compteurs(self):
        url = reverse('avis_admin:reclamation_list')
        response = self.client.get(url)
        self.assertEqual(response.context['compteurs']['ouverte'], 1)
        self.assertEqual(len(self.client.get(url, {'statut': 'resolue'}).context['page']), 0)
        self.assertEqual(len(self.client.get(url, {'motif': 'retard'}).context['page']), 1)
        self.assertEqual(len(self.client.get(url, {'q': 'AgroMed'}).context['page']), 1)
        self.assertEqual(len(self.client.get(url, {'q': 'introuvable'}).context['page']), 0)

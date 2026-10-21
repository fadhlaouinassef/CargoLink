from datetime import date

from django.test import TestCase
from django.urls import reverse

from authentification.models import User
from demandes.models import DemandeTransport

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

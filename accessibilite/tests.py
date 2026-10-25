from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from django.contrib.staticfiles import finders
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.templatetags.static import static
from django.test import RequestFactory, SimpleTestCase, TestCase

from .middleware import CLE_STOCKAGE, AccessibiliteMiddleware

PAGE = '<!DOCTYPE html><html><head><title>t</title></head><body><main>Bonjour</main></body></html>'
CSS = static('accessibilite/accessibilite.css')
JS = static('accessibilite/accessibilite.js')


def passer_par_le_middleware(reponse):
    return AccessibiliteMiddleware(lambda requete: reponse)(RequestFactory().get('/'))


class InjectionDansLesPagesTests(SimpleTestCase):
    def test_page_complete_recoit_la_feuille_de_style_et_le_script(self):
        html = passer_par_le_middleware(HttpResponse(PAGE)).content.decode()
        self.assertEqual(html.count(CSS), 1)
        self.assertEqual(html.count(JS), 1)
        self.assertLess(html.index(CSS), html.index('</head>'))          # feuille de style dans <head>
        self.assertLess(html.index(JS), html.index('</body>'))           # script en fin de <body>
        self.assertIn('<main>Bonjour</main>', html)                      # le contenu d'origine est intact

    def test_l_etat_memorise_est_applique_des_le_head(self):
        html = passer_par_le_middleware(HttpResponse(PAGE)).content.decode()
        script = html[html.index('<script>'):html.index('</head>')]
        self.assertIn(f'localStorage.getItem("{CLE_STOCKAGE}")', script)
        self.assertIn('a11y-contraste', script)

    def test_balises_en_majuscules(self):
        page = PAGE.replace('</head>', '</HEAD>').replace('</body>', '</BODY >')
        html = passer_par_le_middleware(HttpResponse(page)).content.decode()
        self.assertEqual((html.count(CSS), html.count(JS)), (1, 1))

    def test_pas_de_double_injection(self):
        premiere = passer_par_le_middleware(HttpResponse(PAGE))
        html = passer_par_le_middleware(premiere).content.decode()
        self.assertEqual((html.count(CSS), html.count(JS)), (1, 1))

    def test_le_script_est_ajoute_avant_la_derniere_balise_body(self):
        page = '<html><head></head><body><script>var s = "</body>";</script><p>fin</p></body></html>'
        html = passer_par_le_middleware(HttpResponse(page)).content.decode()
        self.assertTrue(html.rstrip().endswith(f'<script src="{JS}"></script></body></html>'))

    def test_content_length_est_mis_a_jour(self):
        reponse = HttpResponse(PAGE)
        reponse['Content-Length'] = str(len(PAGE))
        reponse = passer_par_le_middleware(reponse)
        self.assertEqual(reponse['Content-Length'], str(len(reponse.content)))

    def test_codes_d_erreur_html_sont_traites_comme_les_autres_pages(self):
        reponse = passer_par_le_middleware(HttpResponse(PAGE, status=404))
        self.assertEqual(reponse.status_code, 404)
        self.assertIn(JS, reponse.content.decode())


class ReponsesQuiNeDoiventPasEtreModifieesTests(SimpleTestCase):
    def verifier_intacte(self, reponse):
        avant = None if getattr(reponse, 'streaming', False) else reponse.content
        resultat = passer_par_le_middleware(reponse)
        self.assertIs(resultat, reponse)
        if avant is not None:
            self.assertEqual(resultat.content, avant)

    def test_json(self):
        self.verifier_intacte(JsonResponse({'html': PAGE}))

    def test_pdf(self):
        self.verifier_intacte(HttpResponse(b'%PDF-1.7 </head></body>', content_type='application/pdf'))

    def test_texte_brut(self):
        self.verifier_intacte(HttpResponse(PAGE, content_type='text/plain'))

    def test_redirection(self):
        self.verifier_intacte(HttpResponseRedirect('/connexion/'))

    def test_telechargement_html(self):
        reponse = HttpResponse(PAGE)
        reponse['Content-Disposition'] = 'attachment; filename="rapport.html"'
        self.verifier_intacte(reponse)

    def test_fragment_html_sans_head_ni_body(self):
        self.verifier_intacte(HttpResponse('<div class="popup"><p>Contenu</p></div>'))

    def test_page_sans_balise_body(self):
        self.verifier_intacte(HttpResponse('<html><head></head><p>incomplète</p></html>'))

    def test_reponse_en_flux(self):
        self.verifier_intacte(StreamingHttpResponse(iter([PAGE.encode()]), content_type='text/html'))

    def test_une_erreur_de_fichiers_statiques_ne_casse_pas_la_page(self):
        reponse = HttpResponse(PAGE)
        with mock.patch('accessibilite.middleware.static', side_effect=ValueError('manifeste incomplet')):
            self.assertEqual(passer_par_le_middleware(reponse).content.decode(), PAGE)


class SurLesVraiesPagesTests(TestCase):
    def test_pages_publiques_recoivent_le_bouton(self):
        for url in ('/', '/signin/', '/register/', '/forget-password/'):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertEqual((html.count(CSS), html.count(JS)), (1, 1))

    def test_fichiers_statiques_presents(self):
        self.assertIsNotNone(finders.find('accessibilite/accessibilite.css'))
        self.assertIsNotNone(finders.find('accessibilite/accessibilite.js'))
        with open(finders.find('accessibilite/accessibilite.js'), encoding='utf-8') as fichier:
            script = fichier.read()
        with open(finders.find('accessibilite/accessibilite.css'), encoding='utf-8') as fichier:
            styles = fichier.read()
        self.assertIn('a11y-help-tooltip', script)
        self.assertIn("label.querySelector('.portal-label') || label", script)
        self.assertIn('aria-describedby', script)
        self.assertIn('.a11y-help-label', styles)
        self.assertIn(':focus-visible + .a11y-help-tooltip', styles)

    def test_meme_cle_de_memorisation_dans_le_script_et_dans_le_middleware(self):
        with open(finders.find('accessibilite/accessibilite.js'), encoding='utf-8') as fichier:
            self.assertIn(f"var CLE = '{CLE_STOCKAGE}';", fichier.read())

    def test_le_bouton_est_masque_a_l_impression(self):
        with open(finders.find('accessibilite/accessibilite.css'), encoding='utf-8') as fichier:
            css = fichier.read()
        self.assertIn('@media print', css)

    def test_toutes_les_images_des_templates_ont_un_texte_alternatif(self):
        class Images(HTMLParser):
            def __init__(self):
                super().__init__()
                self.images_sans_alt = []

            def handle_starttag(self, tag, attrs):
                if tag == 'img' and 'alt' not in dict(attrs):
                    self.images_sans_alt.append(self.get_starttag_text())

        racine = Path(__file__).resolve().parent.parent
        parser = Images()
        repertoires_templates = [
            racine / 'templates',
            racine / 'authentification' / 'templates',
            racine / 'avis_reclamations' / 'templates',
            racine / 'demandes' / 'templates',
            racine / 'gestion_trajets_offres' / 'templates',
        ]
        for repertoire in repertoires_templates:
            for template in repertoire.rglob('*.html'):
                parser.feed(template.read_text(encoding='utf-8'))
        self.assertEqual(parser.images_sans_alt, [])

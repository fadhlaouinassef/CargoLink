"""Ajoute le bouton « Accessibilité » (contraste lisible) à toutes les pages HTML du site.

L'ajout se fait ici, sur la réponse, plutôt que dans chaque gabarit : les pages des autres modules
n'ont pas à être modifiées, et toute nouvelle page reçoit le bouton automatiquement.
Seules les pages HTML complètes (avec <head> et <body>) sont concernées ; les réponses JSON, PDF,
téléchargements, redirections et fragments HTML restent strictement identiques.
"""
import re

from django.templatetags.static import static

MARQUEUR = b'data-a11y-injecte'
FIN_HEAD = re.compile(rb'</head\s*>', re.IGNORECASE)
FIN_BODY = re.compile(rb'</body\s*>', re.IGNORECASE)

# Même clé que dans static/accessibilite/accessibilite.js : le choix de l'utilisateur est mémorisé dans son navigateur.
CLE_STOCKAGE = 'cargolink-contraste'


class AccessibiliteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.injecter(self.get_response(request))

    def injecter(self, response):
        if getattr(response, 'streaming', False) or not response.get('Content-Type', '').startswith('text/html'):
            return response
        if 'attachment' in response.get('Content-Disposition', '').lower():
            return response
        contenu = response.content
        if MARQUEUR in contenu:
            return response
        fin_head = FIN_HEAD.search(contenu)
        fins_body = list(FIN_BODY.finditer(contenu))
        if not fin_head or not fins_body:
            return response  # fragment HTML, pas une page complète
        fin_body = fins_body[-1]
        try:
            css, js = static('accessibilite/accessibilite.css'), static('accessibilite/accessibilite.js')
        except ValueError:
            return response  # fichiers statiques non collectés : la page doit s'afficher normalement

        # Dans <head> : la feuille de style, et l'état mémorisé appliqué tout de suite pour éviter un flash.
        entete = (
            f'<link rel="stylesheet" href="{css}" data-a11y-injecte>'
            f'<script>try{{if(localStorage.getItem("{CLE_STOCKAGE}")==="1")'
            f'document.documentElement.classList.add("a11y-contraste")}}catch(e){{}}</script>'
        ).encode('utf-8')
        pied = f'<script src="{js}"></script>'.encode('utf-8')
        response.content = (
            contenu[:fin_head.start()] + entete + contenu[fin_head.start():fin_body.start()]
            + pied + contenu[fin_body.start():]
        )
        if response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))
        return response

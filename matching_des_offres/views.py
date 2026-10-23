"""Point d'accès JSON du classement des offres reçues pour une demande (alimente le popup de la PME).

Le modèle et ses bibliothèques (scikit-learn, pandas…) sont importés au dernier moment, dans la vue :
si elles manquent, seul ce classement est indisponible et le reste du site continue de fonctionner.
"""
import logging

from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from authentification.models import User
from demandes.models import DemandeTransport
from gestion_trajets_offres.models import OffreTransport
from vehicules.models import Vehicule

logger = logging.getLogger(__name__)

AVERTISSEMENT_SCORE = (
    "Le score est un indicateur de classement entre les offres admissibles de cette demande ; "
    "ce n'est pas une probabilité de réussite du transport."
)

MESSAGES = {
    'ok': "Offres admissibles classées par score décroissant.",
    'aucune_offre': "Aucune offre n'a encore été reçue pour cette demande.",
    'aucune_offre_admissible': (
        "Aucune offre reçue ne respecte les contraintes de cette demande. "
        "Consultez les motifs d'exclusion de chaque offre."
    ),
    'donnees_insuffisantes': (
        "Les données de la demande sont insuffisantes pour évaluer les offres. "
        "Complétez la demande (marchandises, poids et volume) puis réessayez."
    ),
    'modele_indisponible': (
        "Le classement automatique est momentanément indisponible. "
        "Vous pouvez consulter et comparer les offres sans classement."
    ),
}


def _erreur(http, code, message):
    return JsonResponse({'statut': code, 'message': message}, status=http)


def _reponse(statut, demande, http=200, **contenu):
    return JsonResponse({
        'statut': statut,
        'message': MESSAGES[statut],
        'demande': {
            'id': demande.pk,
            'reference': str(demande),
            'depart': demande.depart_ville,
            'arrivee': demande.arrivee_ville,
            'date_depart': demande.date_depart.isoformat(),
            'date_limite': demande.date_limite.isoformat(),
            'budget': float(demande.budget) if demande.budget is not None else None,
        },
        'avertissement': AVERTISSEMENT_SCORE,
        'offres': [],
        'exclues': [],
        'non_evaluables': [],
        **contenu,
    }, status=http)


def _identite(offre):
    trajet = offre.trajet
    return {
        'offre_id': offre.pk,
        'reference': f'OFF-{offre.pk}',
        'transporteur': {'id': offre.transporteur_id, 'nom': offre.transporteur.full_name},
        'prix': float(offre.prix),
        'trajet': {
            'depart': trajet.depart_ville,
            'arrivee': trajet.arrivee_ville,
            'date_depart': trajet.date_depart.isoformat(),
        },
        'vehicule_reference': trajet.vehicule,
        'capacites': {
            'poids_kg': float(trajet.capacite_kg),
            'volume_m3': float(trajet.volume_m3),
        },
        'statut_offre': offre.statut,
    }


def _critere(code, libelle, verifie, detail=''):
    """`verifie` vaut True (vérifié), False (non respecté) ou None (non vérifiable avec les données disponibles)."""
    return {'code': code, 'libelle': libelle, 'verifie': verifie, 'detail': detail}


def _criteres(resultat, demande, vehicule_reference):
    """Critères réellement contrôlés pour une offre admissible, avec leurs limites."""
    if demande.budget is None:
        budget = _critere('budget', 'Budget indicatif', None, "Aucun budget n'a été indiqué pour cette demande.")
    elif resultat.depasse_budget:
        budget = _critere('budget', 'Budget indicatif', False, f"Prix supérieur au budget indicatif de {demande.budget} TND.")
    else:
        budget = _critere('budget', 'Budget indicatif', True)
    return [
        _critere('trajet', 'Trajet compatible', True, 'Mêmes villes de départ et d’arrivée.'),
        _critere('creneau', 'Créneau compatible', True, 'Départ du trajet dans la période de la demande.'),
        _critere('capacites', 'Capacités suffisantes', True,
                 'Poids et volume comparés à la capacité déclarée du trajet (les réservations déjà acceptées ne sont pas déduites).'),
        (_critere('vehicule', 'Véhicule disponible', True) if vehicule_reference
         else _critere('vehicule', 'Véhicule disponible', None, 'Véhicule non référencé dans le catalogue : disponibilité non vérifiée.')),
        _critere('marchandise', 'Marchandise compatible', True),
        budget,
    ]


def _offre_classee(resultat, demande, vehicules, peut_accepter):
    offre = resultat.offre
    vehicule = vehicules.get(offre.trajet.vehicule)
    vehicule_reference = vehicule is not None
    donnees = _identite(offre)
    donnees['transporteur'].update({'note': resultat.note_transporteur, 'nombre_avis': resultat.nombre_avis})
    donnees.update({
        'rang': resultat.rang,
        'score': resultat.score,
        'pertinent_predit': resultat.pertinent_predit,
        'depasse_budget': resultat.depasse_budget,
        # Un véhicule hors catalogue reçoit un type par défaut dans le service : on ne l'affiche pas.
        'type_vehicule': resultat.type_vehicule if vehicule_reference else None,
        'details_vehicule': {
            'description': f'{vehicule.marque} {vehicule.modele}',
            'type': vehicule.get_type_vehicule_display(),
        } if vehicule_reference else None,
        'criteres': _criteres(resultat, demande, vehicule_reference),
        'url_accepter': (
            reverse('pme:accepter_offre', args=[demande.pk, offre.pk])
            if peut_accepter and offre.statut == OffreTransport.Statut.EN_ATTENTE else None
        ),
    })
    return donnees


def _offre_ecartee(resultat):
    return {**_identite(resultat.offre), 'motifs': resultat.motifs_rejet}


@never_cache
@require_GET
def offres_classees(request, pk):
    """Offres admissibles classées, offres exclues avec leurs motifs, offres non évaluables."""
    if not request.user.is_authenticated:
        return _erreur(401, 'non_authentifie', 'Connexion requise.')
    if request.user.role != User.Role.PME:
        return _erreur(403, 'acces_refuse', 'Cette fonctionnalité est réservée aux PME.')
    # Une demande inexistante et une demande d'une autre PME reçoivent la même réponse.
    demande = DemandeTransport.objects.prefetch_related('marchandises').filter(pk=pk, created_by=request.user).first()
    if demande is None:
        return _erreur(404, 'demande_introuvable', 'Demande introuvable.')

    # Offres encore en jeu : les offres refusées ne sont pas reclassées.
    offres = list(
        demande.offres_transport
        .filter(statut__in=[OffreTransport.Statut.EN_ATTENTE, OffreTransport.Statut.ACCEPTEE])
        .select_related('transporteur', 'trajet')
    )
    if not offres:
        return _reponse('aucune_offre', demande)

    try:
        from matching_des_offres import services  # import tardif : bibliothèques du modèle facultatives
        resultat = services.evaluate_and_rank_offres(demande, offres)
    except Exception:  # fichier absent ou illisible, bibliothèque manquante, version incompatible…
        logger.exception("Classement des offres indisponible pour la demande %s", demande.pk)
        return _reponse('modele_indisponible', demande, http=503)

    vehicules = {
        vehicule.immatriculation: vehicule
        for vehicule in Vehicule.objects.filter(
            immatriculation__in={offre.trajet.vehicule for offre in offres}
        )
    }
    peut_accepter = (
        demande.statut == DemandeTransport.Statut.OUVERTE
        and not any(offre.statut == OffreTransport.Statut.ACCEPTEE for offre in offres)
    )
    classees = [_offre_classee(r, demande, vehicules, peut_accepter) for r in resultat['classement']]
    exclues = [_offre_ecartee(r) for r in resultat['offres_exclues'] if not r.donnees_insuffisantes]
    non_evaluables = [_offre_ecartee(r) for r in resultat['offres_exclues'] if r.donnees_insuffisantes]

    if classees:
        statut = 'ok'
    elif non_evaluables:
        statut = 'donnees_insuffisantes'
    else:
        statut = 'aucune_offre_admissible'
    return _reponse(
        statut, demande,
        offres=classees, exclues=exclues, non_evaluables=non_evaluables,
        modele={'seuil_pertinence': round(resultat['threshold'], 4)},
    )

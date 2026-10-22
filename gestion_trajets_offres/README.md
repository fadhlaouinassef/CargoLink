# Gestion des trajets et des offres

Chaque transporteur gère ses propres trajets et offres sous `/transporteur/`.
La route GET `/pme/demandes/<pk>/offres/` affiche les offres reçues dans une popup,
uniquement pour le propriétaire de la demande (compte ou session).
Dans cette popup, « Accepter » envoie un POST protégé par CSRF : l'offre choisie
est acceptée et les autres offres en attente deviennent non retenues, dans une
transaction. La demande n'est alors plus proposée aux transporteurs.

- `/transporteur/demandes/` : demandes ouvertes créées par des PME, recherche et candidature.
- `/transporteur/trajets/` : ajout, modification et suppression des trajets en popup.
- `/transporteur/offres/` : consultation, modification et suppression des offres en attente.
- `/transporteur/transports/` : état enregistré des trajets et mise à jour en popup.

Le module Python est `gestion_trajets_offres`. Le label Django `gestion_trajets`
est conservé pour préserver les migrations et les données existantes.
Les deux tables sont `gestion_trajets_trajet` et
`gestion_trajets_offretransport`. Les offres référencent les demandes existantes
de l’application `demandes`. Un transporteur peut proposer une seule offre par
demande et doit choisir un de ses trajets publiés, avec un itinéraire, une date
et une capacité compatibles. Les offres acceptées ne sont plus modifiables ni
supprimables ; un trajet lié à une offre est protégé contre la suppression.

Les formulaires utilisent la validation Django et la protection CSRF. Le
JavaScript charge les popups et affiche un spinner pendant les requêtes.
La suppression exige une confirmation puis une requête POST.

```powershell
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py test gestion_trajets_offres
```

Le suivi conserve l’état courant et la date de dernière mise à jour du trajet.

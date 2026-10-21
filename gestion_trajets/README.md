# Gestion des trajets et suivi

Application réservée aux utilisateurs avec le rôle `transporteur`. Toutes ses
routes sont montées sous `/transporteur/` ; chaque transporteur gère ses propres
trajets et offres.

- `/transporteur/demandes/` : demandes ouvertes créées par des PME, recherche et candidature.
- `/transporteur/trajets/` : ajout, modification et suppression des trajets en popup.
- `/transporteur/offres/` : consultation, modification et suppression des offres en attente.
- `/transporteur/transports/` : état enregistré des trajets et mise à jour en popup.

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
.venv/Scripts/python.exe manage.py test gestion_trajets
```

Le suivi conserve l’état courant et la date de dernière mise à jour du trajet.

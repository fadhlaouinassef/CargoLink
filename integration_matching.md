# Étape 4 — sécurisation du choix d’une offre

L’acceptation reste dans le parcours PME existant (`pme:accepter_offre`) et s’exécute dans une transaction. Le modèle de matching sert uniquement à classer les offres dans le popup ; son score n’est pas une probabilité de réussite et ses recommandations ne sont pas validées sur des décisions réelles.

## Contrôles à la confirmation

Au POST, le serveur vérifie de nouveau que la PME possède la demande, que celle-ci est ouverte, que l’offre est encore en attente et qu’aucune autre offre n’a déjà été acceptée. Il verrouille la demande, le véhicule référencé par le trajet, les indisponibilités et les maintenances correspondantes. Il contrôle ensuite que le trajet est publié et à venir, que sa date est dans la période demandée, que le véhicule existe toujours, appartient au transporteur et est actif, et que le poids et le volume connus tiennent dans les capacités du trajet et du véhicule.

Les indisponibilités explicites et les maintenances planifiées ou en cours bloquent la confirmation. Une offre déjà acceptée pour le même véhicule à la même date de départ la bloque aussi. Le modèle ne conserve pas de durée de trajet : le conflit est donc vérifié à la journée de départ, règle conservatrice documentée ici. Le volume absent reste absent ; le contrôle de volume n’est fait que si les marchandises ont une valeur connue. Un échec renvoie HTTP 409 avec un motif et ne modifie pas les offres.

La transaction et le verrouillage du véhicule sérialisent les confirmations concurrentes sur les bases qui prennent en charge `SELECT FOR UPDATE`. SQLite ignore ce verrouillage ; la suite de tests SQLite vérifie les règles fonctionnelles, pas la concurrence réelle en production.

## Tests

Commande complète :

```powershell
.venv\Scripts\python.exe manage.py test gestion_trajets_offres matching_des_offres
```

Résultat observé pendant l’intégration : **échec de la suite**. Les tests de `matching_des_offres` ne s’importent pas dans l’environnement courant (`joblib` et `numpy` absents). Parmi les tests de `gestion_trajets_offres`, un test existant sans rapport avec l’acceptation échoue (`test_list_only_open_pme_demands_and_search`, attendu 404, reçu 200). Django n’a signalé aucune erreur de configuration.

Les quatre tests ciblés ci-dessous ont ensuite été exécutés avec succès : **4 tests, OK**.

Tests ciblés à lancer après installation des dépendances du projet :

```powershell
.venv\Scripts\python.exe manage.py test `
  gestion_trajets_offres.tests.GestionTrajetsTests.test_accept_offer_updates_popup_and_rejects_other_offers `
  gestion_trajets_offres.tests.GestionTrajetsTests.test_accept_offer_checks_owner_demand_status_and_csrf `
  gestion_trajets_offres.tests.GestionTrajetsTests.test_accept_offer_rechecks_route_vehicle_and_capacities `
  gestion_trajets_offres.tests.GestionTrajetsTests.test_accept_offer_rejects_vehicle_unavailability_and_duplicate_booking
```

Ces scénarios couvrent la confirmation et la mise à jour du popup, les doubles POST, l’accès hors propriétaire, la demande fermée, CSRF, la capacité devenue insuffisante, le trajet annulé, l’indisponibilité déclarée et un véhicule déjà réservé le même jour. Le parcours de classement complet n’a pas pu être validé dans cet environnement tant que les dépendances du modèle ne sont pas installées.

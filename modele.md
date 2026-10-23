# Modèle de matching des offres — version 2

Le modèle reste autonome dans `matching_des_offres/` : aucune interface, route, migration, lecture de base ou activation dans les paramètres Django.

## Commandes avec uv

Depuis la racine du projet, dans PowerShell :

```powershell
uv pip install --python .venv\Scripts\python.exe -r matching_des_offres\requirements.txt

# Lecture effective des 100 expéditions du CSV, puis simulation des offres manquantes.
uv run --no-sync python -m matching_des_offres generate --source datasets\shippments_dataset.csv --offers-per-request 30 --seed 42

# Train : optimisation de précision sur validation, avec rappel minimal de 50 %.
uv run --no-sync python -m matching_des_offres train --min-recall 0.5 --seed 42

# Précision et autres métriques sur le test réservé.
uv run --no-sync python -m matching_des_offres evaluate

# Prédiction et tests.
uv run --no-sync python -m matching_des_offres predict --input matching_des_offres\exemple.json
uv run --no-sync python -m unittest matching_des_offres.tests -v
```

Si le venv n'existe pas, le créer avec `uv venv --python 3.13 .venv`. Garder `--no-sync` : les bibliothèques du modèle sont dans son `requirements.txt`, indépendamment du `pyproject.toml` Django. Le parcours détaillé est dans [scenario.md](scenario.md).

## Utilisation du dataset : ce qui est réellement lu

La version initiale utilisait uniquement une simulation. **La version 2 lit par défaut `datasets/shippments_dataset.csv`**, sans modifier ce fichier.

Le CSV contient 100 expéditions. La préparation transforme chaque expédition en une demande et lui associe 30 offres fictives, soit 3 000 couples. Une expédition correspond toujours au même groupe : aucune de ses offres n'est répartie entre apprentissage et test.

| Champ CSV | Utilisation |
| --- | --- |
| `shipment_id` | Identifiant de demande et groupe de séparation |
| `weight_tons` | Poids réel converti en kg (`× 1000`), utilisé dans les contraintes et le ratio poids/capacité |
| `curr_loc`, `destination`, `route` | Départ, arrivée et route conservés dans les couples préparés |
| `ready_time`, `delivery_deadline` | Dates conservées ; une attente simulée dépassant la fenêtre rend le créneau incompatible |

Les villes et les dates ne sont pas des variables apprises directement. Le prototype ne calcule pas de route, de durée de transport ou de calendrier de véhicule.

**Le CSV n'a ni offres ni cible `pertinent`.** Les prix, budgets, volumes, capacités, avis, catégories, compatibilités et labels sont donc simulés. Le résultat est une démonstration fondée sur des expéditions du CSV, et non un apprentissage des décisions réelles d'utilisateurs. Augmenter le nombre d'offres simulées n'ajoute pas de nouvelles expéditions indépendantes.

La préparation crée :

- `matching_des_offres/data/matching_dataset.json` : couples demande–offre.
- `matching_des_offres/data/matching_dataset.metadata.json` : chemin du CSV, empreinte SHA-256, effectif et distinction entre champs source et simulés.

Lors de `train`, le CSV est **relu** : son empreinte, les identifiants, poids, villes et dates sont comparés aux données préparées. Une incohérence bloque l'entraînement. La preuve est conservée dans `artifacts/rapport.json`, sous `data_provenance` : `source_file`, `source_rows = 100`, `verified_at_training = true`.

## Amélioration de la précision

La version 2 compare huit configurations : régressions logistiques (`C = 0.1, 1, 10`), Random Forest (feuilles minimales de 6, 12 ou 24 exemples) et deux configurations de HistGradientBoosting.

Pour chaque candidat, le seuil de classification est choisi **sur la validation uniquement** afin de maximiser la précision sous un rappel minimal de 50 %. Le modèle est choisi par précision, puis Precision@3 et F1 en cas d'égalité. La contrainte de rappel évite de maximiser la précision en prédisant presque toujours la classe négative. Elle s'applique à la validation et n'est pas une garantie sur de nouvelles données.

Le test reste séparé. Aucun seuil ou hyperparamètre n'est choisi sur ses résultats. Le rapport conserve aussi la mesure au seuil 0,5 et une comparaison avec l'ancienne méthode réentraînée sur les mêmes données et la même séparation.

`--min-recall` permet de changer le compromis. Ne pas chercher un réglage en relançant sur le même test jusqu'à obtenir le chiffre souhaité ; une nouvelle campagne d'optimisation nécessite un nouveau test indépendant.

## Résultats mesurés le 23 octobre 2026

Graine 42, 100 demandes source, 3 000 offres simulées. Séparation : 60 demandes d'entraînement, 20 de validation, 20 de test, sans recouvrement. Les transformations sont ajustées sur l'entraînement uniquement ; le modèle sauvegardé reste entraîné sur ces 60 demandes.

Modèle retenu : **Random Forest, 250 arbres, minimum 24 exemples par feuille**. Seuil retenu : **0,478388**.

| Mesure sur le même test | Ancienne méthode réentraînée | Version 2 |
| --- | ---: | ---: |
| Précision | 68,87 % | **73,56 %** |
| Accuracy | 75,39 % | **75,70 %** |
| Rappel | 61,34 % | 53,78 % |
| F1 | 0,6489 | 0,6214 |
| Precision@3 | 70,00 % | 70,00 % |

L'ancienne méthode comparait régression logistique et Random Forest selon la Precision@3 de validation, puis utilisait le seuil fixe 0,5. Sur ce nouveau jeu, elle choisit la régression logistique.

Le gain de précision est de **4,70 points**, avec une baisse du rappel et du F1. Le classement simple sans IA obtient une Precision@3 de **75 %**, supérieure à celle du modèle. L'amélioration concerne donc la précision de classification, pas la qualité du top 3.

Ces résultats ne se comparent pas directement aux anciens 69,89 % et 44,82 % : le jeu a changé, avec 100 demandes source et davantage d'offres par demande. Le tableau ci-dessus compare les deux méthodes sur le même nouveau jeu. Le test ne comporte que 20 expéditions et les labels restent simulés : aucun gain réel en production n'est démontré.

Le test compte 600 offres : **279 exclues**, **321 admissibles**, **87 prédites pertinentes**, dont 64 réellement positives selon les labels simulés. **Aucune violation métier** dans le classement. **18 tests automatisés réussis**.

Dans l'exemple Tunis–Sousse, A est première (54,41/100), C deuxième (50,51/100), et B est exclue pour manque de capacité en poids.

## Filtrage, variables et interprétation

Les contraintes excluent les offres incompatibles : poids, volume, trajet, créneau, disponibilité, marchandise et budget strict. Un budget souple dépassé est seulement signalé.

Les variables apprises sont le ratio prix/budget, le budget absent, l'écart horaire, le détour, les ratios poids et volume, la note du transporteur, le nombre d'avis, le type de véhicule et la catégorie de marchandise. Les identifiants et la cible n'en font pas partie. Les données d'avis doivent être antérieures à la décision.

La pipeline contient normalisation et encodage des catégories, avec prise en charge d'une catégorie inconnue. Un budget absent est `null`. Un nouveau transporteur a zéro avis et une note de zéro. Les entrées invalides sont refusées.

La prédiction classe **toutes les offres admissibles**, puis fournit `pertinent_predit` selon le seuil sauvegardé. Un score faible ne constitue pas un rejet métier. Le score sur 100 ne représente pas une probabilité de réussite du transport. Les critères affichés sont les contraintes vérifiées, sans explication causale de la prédiction.

La **précision** est la proportion de pertinents parmi les prédictions positives. Le **rappel** mesure la proportion de pertinents détectés. La **Precision@3** est la moyenne par demande de la proportion de pertinents parmi les trois meilleures offres admissibles ; lorsqu'il y en a moins de trois, elle utilise leur nombre réel. Les demandes sans candidat sont exclues de cette moyenne.

## Artefacts et données annotées

Dans `matching_des_offres/artifacts/` :

- `model.joblib` : pipeline et métadonnées, dont seuil et identifiants d'entraînement/validation.
- `rapport.json` : provenance, paramètres, métriques et comparaison avec l'ancienne méthode.
- `split_ids.json` : identifiants des trois ensembles.
- `test.json` : test réservé à rejouer avec `evaluate`.

Les sorties générées sont ignorées par Git et reproductibles avec les commandes. Charger uniquement ses propres fichiers `joblib`.

Pour apprendre de véritables préférences, fournir des couples annotés au format de `exemple.json` avec `pertinent = 0` ou `1`, puis passer `train --data chemin\annotations.json --output matching_des_offres\artifacts_reels`. Prévoir au moins 20 demandes distinctes et les deux classes dans chaque ensemble admissible ; un volume nettement supérieur est préférable. Une évaluation réelle doit aussi réserver une période ultérieure.

Pour retrouver la simulation entièrement fictive, disponible uniquement sur demande explicite :

```powershell
uv run --no-sync python -m matching_des_offres generate --synthetic-only --requests 1200 --output matching_des_offres\data\synthetic.json
uv run --no-sync python -m matching_des_offres train --data matching_des_offres\data\synthetic.json --output matching_des_offres\artifacts_synthetic
```

Versions testées : Python 3.13.14, NumPy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, joblib 1.6.0.

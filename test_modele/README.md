# Tests et captures du modèle de matching

Toutes les commandes s'exécutent **depuis la racine CargoLink**, dans PowerShell. Aucune base Django n'est nécessaire.

## Générer les rapports du modèle déjà entraîné

```powershell
.\.venv\Scripts\python.exe -m test_modele.evaluation
Start-Process .\test_modele\resultats\rapport.html
```

Le script charge `matching_des_offres/artifacts/model.joblib`, c'est-à-dire le modèle par défaut du service Django. Il utilise son **seuil sauvegardé**, sans réentraînement et sans sélectionner un nouveau seuil sur le test. Il vérifie l'empreinte SHA-256 du dataset, les groupes train/validation/test, l'absence de recouvrement et l'identité du test réservé avec les lignes correspondantes du dataset.

Si les bibliothèques manquent, avec uv installé :

```powershell
uv pip install --python .venv\Scripts\python.exe -r test_modele\requirements.txt
```

Alternative si pip est disponible dans le venv :

```powershell
.\.venv\Scripts\python.exe -m pip install -r test_modele\requirements.txt
```

Pillow sert à produire les PNG, sans fenêtre graphique ni dépendance matplotlib. Les images sont des rendus des données et mesures calculées, pas des captures d'écran manuelles.

## Lancer les tests automatisés

```powershell
.\.venv\Scripts\python.exe -m unittest test_modele.test_evaluation matching_des_offres.tests -v
```

Les nouveaux tests vérifient une matrice connue, les formules de précision/rappel/F1, le seuil, les entrées invalides, le cas d'une seule classe, le refus d'une fuite de données et la reproduction des métriques enregistrées du modèle actif. Ils ne fixent pas un objectif arbitraire de précision à atteindre. Les tests existants couvrent notamment les contraintes métier, les données sources et la persistance du modèle.

La commande existante suivante reste disponible pour afficher seulement les métriques numériques :

```powershell
.\.venv\Scripts\python.exe -m matching_des_offres evaluate
```

## Fichiers produits dans `resultats/`

| Fichier / dossier | Contenu |
| --- | --- |
| `rapport.html` | Galerie locale des captures et explications |
| `rapport_evaluation.json` | Scores train/validation/test, matrices, classification report, empreintes, effectifs, provenance |
| `rapport_entrainement_original.json` | Métadonnées du modèle enregistrées pendant son entraînement |
| `captures/confusion_train.png`, `confusion_validation.png`, `confusion_test.png` | Matrices brutes, uniquement sur offres admissibles |
| `captures/confusion_test_normalisee.png` | Matrice test normalisée par classe réelle |
| `captures/courbe_roc_test.png` | ROC et comparaison au score de référence fixe |
| `captures/courbe_precision_rappel_test.png` | Courbe précision-rappel ; AP indiquée dans le sous-titre |
| `captures/precision_test.png` | Accuracy, précision, rappel, F1, AUC ROC, Precision@3 |
| `captures/train_validation_test.png` | Comparaison des scores du modèle sauvegardé sur les trois ensembles |
| `captures/comparaison_entrainement.png` | Candidats et seuils comparés sur validation pendant l'entraînement |
| `captures/apercu_dataset.png`, `apercu_source_csv.png` | Extraits tabulaires du dataset préparé et du CSV source |
| `captures/repartition_dataset.png`, `classes_dataset.png` | Répartition des ensembles, filtrage et classes |
| `captures/correlations_train.png` | Matrice de corrélation descriptive sur train ; tiret pour variable constante |
| `exports/` | Prédictions par offre (y compris motifs d'exclusion), métriques, matrices, classification reports et extraits CSV |

ROC et précision-rappel nécessitent deux classes sur test et ne sont générées que dans ce cas. L'aperçu du CSV source est généré si le modèle conserve cette provenance. Pour un CSV déplacé, utiliser `--source chemin\shippments_dataset.csv` avec le même contenu qu'à l'entraînement.

`train_validation_test.png` **n'est pas une courbe d'apprentissage par époque** : le code d'entraînement actuel ne conserve pas cet historique. Les scores train sont mesurés sur les données apprises ; les scores validation ont participé au choix du modèle et du seuil. Le test réservé sert à l'évaluation finale. Les corrélations décrivent des associations, sans explication causale.

## Réentraîner dans ce dossier, sans remplacer le modèle actif

Cette étape est facultative : le modèle existe déjà. Pour une expérience reproductible dans un dossier séparé :

```powershell
.\.venv\Scripts\python.exe -m matching_des_offres generate --source datasets\shippments_dataset.csv --offers-per-request 30 --seed 42 --output test_modele\experience\matching_dataset.json
.\.venv\Scripts\python.exe -m matching_des_offres train --data test_modele\experience\matching_dataset.json --output test_modele\experience\artifacts --seed 42 --min-recall 0.5
.\.venv\Scripts\python.exe -m test_modele.evaluation --data test_modele\experience\matching_dataset.json --artifacts test_modele\experience\artifacts --output test_modele\experience\resultats
```

Pour une nouvelle expérience, utiliser un nouveau dossier de sortie. Ne pas régler les paramètres en fonction du test réservé : les réglages se font sur validation. Le seuil retenu maximise la précision de validation avec rappel minimal de 50 % par défaut ; ce rappel n'est pas garanti sur test.

## Interprétation

Les **labels `pertinent` sont simulés**, ainsi que les offres. Le CSV source fournit des expéditions, sans décisions de pertinence d'utilisateurs. Les chiffres obtenus mesurent donc une simulation, pas la performance réelle en production. Une validation métier nécessite des couples demande-offre réellement annotés et un test indépendant.

La classification IA est évaluée **après filtrage métier** : les offres incompatibles ne sont pas ajoutées à la matrice comme vrais négatifs. Les exclusions sont comptées séparément et exportées avec leurs motifs.

Une matrice s'interprète avec **lignes = réel, colonnes = prédit**, classes `[0, 1]` :

| | Prédit 0 | Prédit 1 |
| --- | --- | --- |
| Réel 0 | Vrais négatifs (VN) | Faux positifs (FP) |
| Réel 1 | Faux négatifs (FN) | Vrais positifs (VP) |

- **Précision** = VP / (VP + FP) : part des offres prédites pertinentes qui le sont selon les labels.
- **Rappel** = VP / (VP + FN) : part des offres pertinentes retrouvées.
- **Accuracy** = (VP + VN) / total : part de toutes les classifications correctes.
- **F1** : moyenne harmonique précision/rappel.
- **AUC ROC** : qualité de discrimination à travers les seuils.
- **Average precision (AP)** : résumé de la courbe précision-rappel, distinct de l'aire calculée par trapèzes.
- **Precision@3** : proportion pertinente dans les trois premières offres, moyennée par demande ayant des offres admissibles (moins de trois : nombre disponible).

Les sorties par défaut sont conservées dans ce dossier pour consultation immédiate et peuvent être régénérées avec la première commande.

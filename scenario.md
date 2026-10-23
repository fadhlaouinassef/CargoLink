# Scénario complet avec uv — version 2

Ce scénario prépare le dataset du dossier **`datasets`**, entraîne le modèle, mesure sa précision et teste les règles métier, uniquement dans le terminal PowerShell.

## 1. Préparer l'environnement

```powershell
Set-Location 'C:\Users\nasse\Desktop\Django\CargoLink'
uv --version
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    uv venv --python 3.13 .venv
}
uv pip install --python .venv\Scripts\python.exe -r matching_des_offres\requirements.txt
uv run --no-sync python -m matching_des_offres --help
```

Conserver `--no-sync` pour garder les bibliothèques du modèle, définies dans son `requirements.txt` et indépendantes du projet Django. Aucun serveur ou accès à la base n'est nécessaire.

## 2. Lire le CSV et préparer les couples

```powershell
uv run --no-sync python -m matching_des_offres generate --source datasets\shippments_dataset.csv --offers-per-request 30 --seed 42
```

Attendu dans le terminal :

- `source_file` se termine par `datasets\shippments_dataset.csv`.
- `source_rows` vaut **100** ; `requests` vaut **100** ; `rows` vaut **3000**.
- `labels_synthetic` vaut **true**.

Le CSV est effectivement lu. Chaque demande reprend son identifiant d'expédition, son poids converti en kg, ses villes et ses dates. Les offres, prix, capacités, volumes, avis et labels absents du CSV sont simulés et identifiés comme tels. Le fichier CSV reste inchangé.

Les sorties sont `matching_des_offres/data/matching_dataset.json` et `matching_dataset.metadata.json`. Le paramètre `--requests` concerne uniquement l'option `--synthetic-only` ; en mode CSV, toutes les expéditions sont utilisées une fois, avec le nombre d'offres demandé.

## 3. Entraîner en privilégiant la précision

```powershell
uv run --no-sync python -m matching_des_offres train --min-recall 0.5 --seed 42
```

Attendu : comparaison de huit configurations, sélection sur validation et sauvegarde dans `matching_des_offres/artifacts/`. La séparation porte sur les expéditions source : **60 entraînement / 20 validation / 20 test**. Les offres d'une même expédition restent ensemble.

Le seuil maximise la précision de validation en conservant au moins 50 % de rappel sur cette validation. Ce minimum n'est pas une garantie sur de nouvelles données. Ne pas ajuster les paramètres à partir des résultats du test.

Dans l'exécution de référence : `selected_model = random_forest_leaf_24`, `threshold ≈ 0.478388`. Les versions des bibliothèques peuvent modifier le résultat.

## 4. Prouver la lecture du dataset à l'entraînement

```powershell
$rapport = Get-Content matching_des_offres\artifacts\rapport.json -Raw -Encoding UTF8 | ConvertFrom-Json
$rapport.data_provenance | Format-List
```

Vérifier : `source_rows = 100`, le chemin du bon CSV et **`verified_at_training = True`**. L'entraînement relit le CSV et compare son empreinte ainsi que les poids, villes, dates et identifiants avec les données préparées. Si le CSV a changé, il exige de relancer `generate`.

## 5. Mesurer la précision sur le test réservé

```powershell
uv run --no-sync python -m matching_des_offres evaluate
```

Résultats de référence :

| Mesure | Attendu |
| --- | ---: |
| Offres totales | 600 |
| Offres exclues | 279 |
| Violations des contraintes | 0 |
| Précision du modèle | 73,56 % |
| Accuracy | 75,70 % |
| Rappel | 53,78 % |
| F1 | 0,6214 |
| Precision@3 | 70,00 % |

Pour comparer avec l'ancienne méthode **réentraînée sur le même jeu** :

```powershell
$rapport.previous_method_test
$rapport.test
$rapport.delta_precision_previous_method
```

La précision passe de **68,87 % à 73,56 %**, soit **+4,70 points**. Le rappel baisse de **61,34 % à 53,78 %**. La Precision@3 reste à 70 % ; le classement fixe sans IA fait 75 %. Les chiffres décrivent des labels simulés, sans garantie de performance réelle. Voir [modele.md](modele.md) pour les détails.

## 6. Tester Tunis → Sousse

Besoin : 350 kg, 2,4 m³, budget de 180 TND. Le fichier d'exemple contient A (170 TND, 600 kg disponibles), B (150 TND, seulement 250 kg disponibles), C (180 TND, 800 kg disponibles).

```powershell
uv run --no-sync python -m matching_des_offres predict --input matching_des_offres\exemple.json
```

Attendu : A première, C deuxième, B exclue pour capacité insuffisante. Scores de référence : A **54,41/100**, C **50,51/100**. `pertinent_predit` est calculé avec le seuil sauvegardé. Les scores ne sont pas des probabilités de réussite du transport.

## 7. Tester des cas métier supplémentaires

Ces commandes créent des copies dans `data/`, sans modifier l'exemple original. Exécuter la création puis la prédiction pour chaque cas.

### Budget strict dépassé

```powershell
uv run --no-sync python -c "import json; from pathlib import Path; r=json.loads(Path('matching_des_offres/exemple.json').read_text(encoding='utf-8'))[0]; r.update(offre_id='TEST-BUDGET', prix=200, budget_strict=True); Path('matching_des_offres/data/cas_budget_strict.json').write_text(json.dumps([r]), encoding='utf-8')"
uv run --no-sync python -m matching_des_offres predict --input matching_des_offres\data\cas_budget_strict.json
```

Attendu : classement vide, motif « Budget strict dépassé ».

### Même prix avec budget souple

```powershell
uv run --no-sync python -c "import json; from pathlib import Path; r=json.loads(Path('matching_des_offres/data/cas_budget_strict.json').read_text(encoding='utf-8'))[0]; r.update(offre_id='TEST-SOUPLE', budget_strict=False); Path('matching_des_offres/data/cas_budget_souple.json').write_text(json.dumps([r]), encoding='utf-8')"
uv run --no-sync python -m matching_des_offres predict --input matching_des_offres\data\cas_budget_souple.json
```

Attendu : offre admissible et classée, `depasse_budget = true`. Son éventuel `pertinent_predit = false` ne signifie pas une exclusion métier.

### Véhicule indisponible

```powershell
uv run --no-sync python -c "import json; from pathlib import Path; r=json.loads(Path('matching_des_offres/exemple.json').read_text(encoding='utf-8'))[0]; r.update(offre_id='TEST-INDISPONIBLE', vehicule_disponible=False); Path('matching_des_offres/data/cas_indisponible.json').write_text(json.dumps([r]), encoding='utf-8')"
uv run --no-sync python -m matching_des_offres predict --input matching_des_offres\data\cas_indisponible.json
```

Attendu : classement vide, motif « Véhicule indisponible ».

### Capacité nulle : erreur volontaire

```powershell
uv run --no-sync python -c "import json; from pathlib import Path; r=json.loads(Path('matching_des_offres/exemple.json').read_text(encoding='utf-8'))[0]; r.update(offre_id='TEST-INVALIDE', capacite_kg=0); Path('matching_des_offres/data/cas_invalide.json').write_text(json.dumps([r]), encoding='utf-8')"
uv run --no-sync python -m matching_des_offres predict --input matching_des_offres\data\cas_invalide.json
$LASTEXITCODE
```

Attendu : erreur sur `capacite_kg`, code **2**.

## 8. Exécuter les tests et vérifier la protection contre les fuites

```powershell
uv run --no-sync python -m unittest matching_des_offres.tests -v
```

Attendu : **18 tests réussis**, sans test ignoré. Ils vérifient aussi la conservation des valeurs du CSV, le blocage d'une demande incohérente avec la source et le choix du seuil sous contrainte de rappel.

```powershell
uv run --no-sync python -m matching_des_offres evaluate --data matching_des_offres\data\matching_dataset.json
$LASTEXITCODE
```

Attendu : refus pour demandes déjà utilisées en entraînement/validation, code **2**. C'est le comportement correct. Pour l'évaluation officielle, utiliser `evaluate` sans cet argument.

## 9. Rejouer le parcours principal

```powershell
uv run --no-sync python -m matching_des_offres generate --source datasets\shippments_dataset.csv --offers-per-request 30 --seed 42
uv run --no-sync python -m matching_des_offres train --min-recall 0.5 --seed 42
uv run --no-sync python -m matching_des_offres evaluate
uv run --no-sync python -m matching_des_offres predict
uv run --no-sync python -m unittest matching_des_offres.tests -v
```

`generate` et `train` réécrivent leurs sorties par défaut. Si le modèle existe déjà, commencer par `evaluate`, puis `predict` et les tests.

Dans le terminal utilisateur, le parcours uv précédent a fonctionné. L'environnement de l'assistant refuse l'exécution de `uv.exe` ; les vérifications de cette version ont été exécutées avec le Python du même venv. En cas de module manquant, relancer l'installation et garder `--no-sync`. Si des accents s'affichent mal, utiliser `$env:PYTHONIOENCODING = 'utf-8'` avant les commandes.

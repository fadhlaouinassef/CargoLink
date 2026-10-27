```powershell
uv run --no-sync python -m test_modele.evaluation
```

Évalue le modèle déjà entraîné et génère les métriques, les matrices, les captures et le rapport dans `test_modele/resultats`.

```powershell
uv run --no-sync python -m unittest test_modele.test_evaluation matching_des_offres.tests -v
```

Lance les tests automatisés pour vérifier les calculs des métriques, la séparation des données et le fonctionnement du modèle. Affiche le résultat de chaque test.

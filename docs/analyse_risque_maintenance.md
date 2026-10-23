# Analyse du Risque de Maintenance Assistée par IA — Documentation & Spécifications

> **Périmètre :** Module Véhicules & Disponibilités (`vehicules`).  
> **Vocabulaire obligatoire :** *« Analyse du risque »* et *« Évaluation indicative »*. Aucun terme probabiliste prédictif trompeur (*« prédiction de pannes »*) n'est utilisé.

---

## 1. Architecture Hybride et Principes Directeurs

Le système adopte une architecture en **deux étages étanches et complémentaires** :

1. **Étage 1 — Moteur de Règles Déterministe (`vehicules/ia/risque_regles.py`) :**
   - Calcule des variables techniques objectives à partir de la base de données.
   - Attribue un score de base de 0 à 100 via des règles pondérées transparentes.
   - Génère la liste des facteurs explicatifs avec indication claire du sens de l'impact (+ hausse / - baisse).
   - Gère de façon défensive l'absence ou l'insuffisance de données (plafonnement du score, facteur explicatif dédié, absence de crash).

2. **Étage 2 — Enrichissement par API LLM (`vehicules/ia/risque_assistant.py`) :**
   - Appelle le modèle Gemini configuré côté serveur via `providers.py`.
   - Reçoit en entrée **uniquement** les variables techniques anonymisées et le score déterministe.
   - Génère une recommandation synthétique courte (≤ 400 car.), suggère le cas échéant un motif de maintenance (`Maintenance.Motif`), une fenêtre d'urgence indicative et un indice de confiance.
   - Valide défensivement chaque champ JSON de sortie.
   - En cas d'indisponibilité, de quota ou de timeout, bascule **automatiquement et gracieusement** sur les résultats de l'Étage 1 (*graceful degradation*).
   - Conserve et signale les divergences d'analyse (écart > 1 cran entre règles et IA) sans les masquer.

---

## 2. Minimisation Stricte des Données Personnelles et Sensibles

Conformément aux principes de confidentialité et de minimisation (RGPD / protection des données) :
- **AUCUN** identifiant n'est jamais transmis au prompt LLM : pas d'immatriculation, pas de nom de transporteur, pas de clé primaire, pas d'adresse.
- **AUCUN** champ de texte libre (ex: les `commentaires` de maintenance) n'est injecté dans le prompt utilisateur.
- Le prompt système rappelle explicitement que les données fournies sont purement descriptives et neutres afin de neutraliser les risques d'injection indirecte de prompt.

---

## 3. Modèle de Données et Traçabilité (`AnalyseRisque`)

Chaque analyse réalisée est historisée dans la table `vehicules_analyserisque` :
- `vehicule` : clé étrangère vers le véhicule.
- `niveau` : `'faible'` | `'moyen'` | `'eleve'`.
- `score` : entier de 0 à 100.
- `facteurs` : JSON structuré `[{facteur, impact, explication}]`.
- `recommandation` : texte court indicatif.
- `motif_suggere` : choix valide ou null.
- `urgence` : `'immediate'` | `'sous_7_jours'` | `'sous_30_jours'` | `'aucune'`.
- `source` : `'regles'` | `'ia'`.
- `modele_utilise` : nom du modèle LLM (ex: `gemini-2.5-flash`).
- `divergence` : booléen signalant un désaccord significatif.
- `donnees_hash` : empreinte SHA-256 déterministe des variables d'entrée.
- `duree_ms` : temps de traitement serveur en millisecondes.
- `date_analyse` : horodatage automatique.

---

## 4. Cache par Hash et Économie de Quota

Pour respecter les quotas d'appels API gratuits et réduire la latence :
1. Une empreinte SHA-256 des variables techniques est calculée à chaque demande.
2. Si une analyse datant de moins de 24 heures existe déjà avec le **même hash**, le système réutilise l'enregistrement existant sans refaire d'appel API, sauf si l'utilisateur clique explicitement sur « Actualiser » (`force=True`).

---

## 5. Exécution Asynchrone et Tâches Périodiques (Celery)

### Commandes pour lancer les workers :
```bash
# Lancer le worker Celery (sous Windows, pool 'solo' requis) :
uv run celery -A CargoLink worker -P solo -l info

# Lancer le planificateur nocturne Celery Beat :
uv run celery -A CargoLink beat -l info
```

### Tâches disponibles (`vehicules/tasks.py`) :
- `analyser_vehicule_task(vehicule_id, force=False)` : analyse d'un véhicule individuel en arrière-plan avec retry et backoff exponentiel (10s, 30s, 90s) sur erreur de quota / timeout.
- `analyser_flotte_task()` : analyse cadencée nocturne de l'ensemble de la flotte active (planifiée à 02:00 heure de Tunis dans `CargoLink/celery.py`), respectant une pause paramétrable `IA_RISQUE_PAUSE_SECONDS = 6` secondes entre véhicules pour le quota gratuit Gemini.

### Dégradation si Celery/Redis n'est pas lancé :
Si un transporteur clique sur l'interface alors que Redis ou Celery n'est pas actif chez un développeur, la vue bascule instantanément en exécution synchrone avec repli sur les règles sans bloquer ni lever d'erreur HTTP 500.

---

## 6. Intégration Inter-Modules Découplée

Une fonction utilitaire est fournie pour tout module tiers (ex: `gestion_trajets_offres` ou création d'offres) afin d'afficher un badge préventif :

```python
from vehicules.services import niveau_risque_vehicule

# Recherche instantanée en BDD sans AUCUN appel API
risque = niveau_risque_vehicule(vehicule.pk)
if risque and risque['niveau'] == 'eleve':
    # Afficher un badge d'avertissement ou suggérer une vérification technique
    pass
```

---

## 7. Résultats du Benchmark sur 60 Profils Synthétiques

Un harness d'évaluation reproductible (`vehicules/ia/eval_harness.py`) teste 60 profils types (20 risque faible, 20 modéré, 20 élevé) :
- **Précision globale de classification :** 83.33 % de concordance parfaite sur les profils calibrés.
- **Concordance directionnelle :** 100 % (aucun faux négatif extrême faible ↔ élevé).
- **Temps d'exécution déterministe :** < 1 ms par profil.

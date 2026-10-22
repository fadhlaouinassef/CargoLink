"""Commande Django pour évaluer chiffrée l'assistant IA sur les phrases de test."""
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median

from django.core.management.base import BaseCommand
from django.utils import timezone

from vehicules.ia.assistant import AssistantDisponibilite
from vehicules.ia.evaluation import evaluate_phrase_result
from vehicules.ia.providers import (
    IAQuotaExceededError,
    IATimeoutError,
    get_default_provider,
)


class Command(BaseCommand):
    help = "Évalue chiffrée les performances de l'assistant IA sur le jeu phrases_test.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ensemble",
            type=str,
            default="tous",
            choices=["dev", "holdout", "tous"],
            help="Ensemble de phrases à évaluer (dev, holdout, ou tous).",
        )
        parser.add_argument(
            "--sortie",
            type=str,
            default="evaluation_assistant.csv",
            help="Chemin du fichier CSV de sortie.",
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=1.5,
            help="Pause en secondes entre deux appels API pour respecter le quota.",
        )

    def handle(self, *args, **options):
        ensemble_filtre = options["ensemble"]
        fichier_sortie = options["sortie"]
        pause_seconds = options["pause"]

        data_path = Path(__file__).resolve().parent.parent.parent / "ia" / "phrases_test.json"
        if not data_path.exists():
            self.stderr.write(self.style.ERROR(f"Fichier de test introuvable : {data_path}"))
            return

        with open(data_path, "r", encoding="utf-8") as f:
            test_data = json.load(f)

        ref_str = test_data.get("date_reference", "2026-10-22T09:00:00+01:00")
        reference_dt = datetime.fromisoformat(ref_str)
        self.stdout.write(self.style.NOTICE(f"Date de référence fixe : {reference_dt.isoformat()}"))

        phrases_all = test_data.get("phrases", [])
        if ensemble_filtre != "tous":
            phrases = [p for p in phrases_all if p.get("ensemble") == ensemble_filtre]
        else:
            phrases = phrases_all

        self.stdout.write(
            self.style.NOTICE(
                f"Lancement de l'évaluation sur l'ensemble '{ensemble_filtre}' ({len(phrases)} phrases)..."
            )
        )

        # Fichier cache local pour permettre reprise en cas d'interruption
        cache_file = Path("evaluation_cache.json")
        cached_results = {}
        if cache_file.exists():
            try:
                cached_results = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cached_results = {}

        provider = get_default_provider()
        assistant = AssistantDisponibilite(provider=provider, reference_now=reference_dt)

        evaluations = []
        errors_detail = []

        for idx, item in enumerate(phrases, 1):
            p_id = item["id"]
            phrase_text = item["phrase"]
            attendu = item["attendu"]
            categorie = item["categorie"]
            ensemble = item.get("ensemble", "dev")

            self.stdout.write(f"[{idx}/{len(phrases)}] {p_id} ({categorie}) : \"{phrase_text[:40]}...\" ", ending="")

            if p_id in cached_results:
                self.stdout.write(self.style.SUCCESS("[CACHE]"))
                entry = cached_results[p_id]
            else:
                attempts = 0
                max_attempts = 3
                success = False
                res_data = None
                call_time = 0.0

                while attempts < max_attempts and not success:
                    attempts += 1
                    try:
                        t0 = time.time()
                        system_prompt = assistant.build_system_prompt()
                        user_prompt = f"Phrase du transporteur à analyser :\n\"\"\"{phrase_text}\"\"\""
                        raw_json_str = provider.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
                        call_time = round(time.time() - t0, 3)

                        parsed = assistant.parse_raw_json(raw_json_str)
                        champs, manquants, avertissements = assistant.validate_and_clean_fields(parsed)
                        res_data = {
                            "valid_json": True,
                            "champs": champs,
                            "call_time": call_time,
                        }
                        success = True
                    except IAQuotaExceededError:
                        self.stdout.write(self.style.WARNING(" [429 Quota, attente 10s...] "), ending="")
                        time.sleep(10)
                    except Exception as e:
                        call_time = round(time.time() - t0, 3)
                        res_data = {
                            "valid_json": False,
                            "error": str(e),
                            "champs": {},
                            "call_time": call_time,
                        }
                        success = True

                entry = res_data or {"valid_json": False, "champs": {}, "call_time": 0.0}
                cached_results[p_id] = entry
                cache_file.write_text(json.dumps(cached_results, ensure_ascii=False, indent=2), encoding="utf-8")
                self.stdout.write(self.style.SUCCESS(f"[OK {entry['call_time']}s]"))
                time.sleep(pause_seconds)

            champs_obtenus = entry.get("champs", {})
            eval_metrics = evaluate_phrase_result(attendu, champs_obtenus)

            record = {
                "id": p_id,
                "ensemble": ensemble,
                "categorie": categorie,
                "phrase": phrase_text,
                "valid_json": entry.get("valid_json", False),
                "call_time": entry.get("call_time", 0.0),
                "global_match": eval_metrics["global_match"],
                "has_hallucination": eval_metrics["has_hallucination"],
                "hallucination_fields": ";".join(eval_metrics["hallucination_fields"]),
                "zd_match": eval_metrics["matches"]["zone_depart"],
                "za_match": eval_metrics["matches"]["zone_arrivee"],
                "dd_match": eval_metrics["matches"]["date_debut"],
                "df_match": eval_metrics["matches"]["date_fin"],
                "tv_match": eval_metrics["matches"]["type_vehicule"],
                "attendu_zd": attendu.get("zone_depart"),
                "obtenu_zd": champs_obtenus.get("zone_depart"),
                "attendu_za": attendu.get("zone_arrivee"),
                "obtenu_za": champs_obtenus.get("zone_arrivee"),
                "attendu_dd": attendu.get("date_debut"),
                "obtenu_dd": champs_obtenus.get("date_debut"),
                "attendu_df": attendu.get("date_fin"),
                "obtenu_df": champs_obtenus.get("date_fin"),
                "attendu_tv": attendu.get("type_vehicule"),
                "obtenu_tv": champs_obtenus.get("type_vehicule"),
            }
            evaluations.append(record)

            if not eval_metrics["global_match"]:
                errors_detail.append(record)

        # Export CSV
        csv_file_path = Path(fichier_sortie)
        fieldnames = list(evaluations[0].keys()) if evaluations else []
        with open(csv_file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for r in evaluations:
                writer.writerow(r)

        # Calcul des statistiques globales
        n = len(evaluations)
        if n == 0:
            return

        valid_json_count = sum(1 for e in evaluations if e["valid_json"])
        global_match_count = sum(1 for e in evaluations if e["global_match"])
        hallucination_count = sum(1 for e in evaluations if e["has_hallucination"])

        zd_acc = sum(1 for e in evaluations if e["zd_match"]) / n * 100
        za_acc = sum(1 for e in evaluations if e["za_match"]) / n * 100
        dd_acc = sum(1 for e in evaluations if e["dd_match"]) / n * 100
        df_acc = sum(1 for e in evaluations if e["df_match"]) / n * 100
        tv_acc = sum(1 for e in evaluations if e["tv_match"]) / n * 100

        times = [e["call_time"] for e in evaluations if e["call_time"] > 0]
        avg_time = mean(times) if times else 0.0
        med_time = median(times) if times else 0.0
        max_time = max(times) if times else 0.0

        self.stdout.write("\n" + "=" * 65)
        self.stdout.write(self.style.SUCCESS(f" RAPPORT D'ÉVALUATION IA — ENSEMBLE : {ensemble_filtre.upper()}"))
        self.stdout.write("=" * 65)
        self.stdout.write(f"Nombre de phrases évaluées : {n}")
        self.stdout.write(f"Taux de réponses JSON valides : {valid_json_count}/{n} ({valid_json_count/n*100:.1f}%)")
        self.stdout.write(f"Exactitude globale (phrase 100% correcte) : {global_match_count}/{n} ({global_match_count/n*100:.1f}%)")
        self.stdout.write(f"Taux d'hallucination (valeur non nulle indue) : {hallucination_count}/{n} ({hallucination_count/n*100:.1f}%)")
        self.stdout.write("-" * 65)
        self.stdout.write("Exactitude par champ :")
        self.stdout.write(f"  • zone_depart   : {zd_acc:.1f}%")
        self.stdout.write(f"  • zone_arrivee  : {za_acc:.1f}%")
        self.stdout.write(f"  • date_debut    : {dd_acc:.1f}%")
        self.stdout.write(f"  • date_fin      : {df_acc:.1f}%")
        self.stdout.write(f"  • type_vehicule : {tv_acc:.1f}%")
        self.stdout.write("-" * 65)
        self.stdout.write(f"Temps de réponse (s) : moyen={avg_time:.2f}s | médian={med_time:.2f}s | max={max_time:.2f}s")
        self.stdout.write("-" * 65)

        # Ventilation par catégorie
        categories = sorted(list({e["categorie"] for e in evaluations}))
        self.stdout.write("Résultats par catégorie :")
        for cat in categories:
            cat_items = [e for e in evaluations if e["categorie"] == cat]
            cat_correct = sum(1 for e in cat_items if e["global_match"])
            self.stdout.write(f"  • {cat:<22} : {cat_correct}/{len(cat_items)} ({cat_correct/len(cat_items)*100:.1f}%)")

        self.stdout.write("=" * 65)
        self.stdout.write(self.style.SUCCESS(f"Résultats détaillés exportés dans : {fichier_sortie}\n"))

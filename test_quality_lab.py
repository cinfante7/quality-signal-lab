"""Requirement-linked unit and integration tests; no network or third-party packages."""
import copy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

import quality_lab as q


class DataTests(unittest.TestCase):
    def test_r01_seed_and_schema(self):
        rows = q.generate()
        self.assertEqual(rows, q.generate())
        self.assertNotEqual(rows, q.generate(seed=42))
        self.assertEqual(q.validate(rows)["rows"], 2400)

    def test_r02_reject_invalid_data(self):
        row = q.generate()[0]
        invalid = [[], [row, row]]
        for key, value in (("surface_score", math.nan), ("vibration_mm_s", -1),
                           ("diameter_mm", 12), ("defect", 2), ("batch", 13),
                           ("sample_id", "")):
            candidate = dict(row)
            candidate[key] = value
            invalid.append([candidate])
        invalid.append([{**row, "unexpected": 1}])
        for rows in invalid:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    q.validate(rows)

    def test_r03_batch_isolation(self):
        train, validation, test = q.split(q.generate())
        self.assertEqual([len(g) for g in (train, validation, test)], [1400, 400, 600])
        batches = [{r["batch"] for r in g} for g in (train, validation, test)]
        self.assertEqual(batches, [set(range(1, 8)), {8, 9}, {10, 11, 12}])
        ids = [{r["sample_id"] for r in g} for g in (train, validation, test)]
        self.assertFalse(ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])
        with self.assertRaises(ValueError):
            q.split(train)


class AlgorithmTests(unittest.TestCase):
    def test_r04_rule_boundaries(self):
        row = dict(diameter_mm=10, surface_score=0.65, vibration_mm_s=2.5)
        self.assertEqual(q.baseline(row), 0)
        for key, value in (("diameter_mm", 10.20001), ("diameter_mm", 9.79999),
                           ("surface_score", 0.65001), ("vibration_mm_s", 2.50001)):
            self.assertEqual(q.baseline({**row, key: value}), 1)

    def test_r05_training_learns_and_ignores_identifiers(self):
        rows = [dict(diameter_mm=10, surface_score=s, vibration_mm_s=1.5,
                     defect=int(s > 0.5), sample_id=str(i), batch=1)
                for i, s in enumerate([0.1, 0.2, 0.8, 0.9] * 10)]
        model = q.fit(rows)
        self.assertLess(q.probability(model, rows[0]), 0.2)
        self.assertGreater(q.probability(model, rows[2]), 0.8)
        altered = [{**r, "sample_id": "unrelated", "batch": 12} for r in rows]
        self.assertEqual(model, q.fit(altered))
        self.assertEqual(model["means"][1], sum(r["surface_score"] for r in rows) / len(rows))

    def test_r06_threshold_minimizes_validation_cost(self):
        train, validation, test = q.split(q.generate())
        model = q.fit(train, epochs=20)
        frozen = copy.deepcopy(model)
        threshold, sweep = q.select_threshold(model, validation)
        winner = min(sweep, key=lambda r: (r["cost"], -r["threshold"]))
        self.assertEqual(threshold, winner["threshold"])
        self.assertEqual(len(sweep), 19)
        self.assertEqual(model, frozen)
        # Test labels cannot affect a validation-only selection or trained scaler.
        for row in test:
            row["defect"] = 1 - row["defect"]
            row["surface_score"] = 100
        self.assertEqual(q.select_threshold(model, validation)[0], threshold)
        self.assertEqual(model, frozen)

    def test_r07_confusion_counts_and_zero_denominators(self):
        m = q.metrics([0, 0, 1, 1], [0, 1, 0, 1])
        self.assertEqual([m[k] for k in ("tn", "fp", "fn", "tp", "cost")], [1, 1, 1, 1, 6])
        self.assertEqual(m["precision"], 0.5)
        self.assertEqual(m["recall"], 0.5)
        self.assertEqual(q.metrics([0, 1], [0, 0])["precision"], 0)
        self.assertEqual(q.metrics([0, 0], [0, 1])["recall"], 0)
        for actual, predicted in (([], []), ([1], []), ([2], [1])):
            with self.assertRaises(ValueError):
                q.metrics(actual, predicted)


class PipelineTests(unittest.TestCase):
    def test_r08_outputs_reconcile_and_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first"
            second = Path(temp) / "second"
            result = q.run(first)
            repeat = q.run(second)
            self.assertEqual(result, repeat)
            for filename in ("metrics.json", "synthetic_inspections.csv", "test_predictions.csv",
                             "failure_review.csv", "report.md", "report.html"):
                self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
            with (first / "test_predictions.csv").open(newline="", encoding="utf-8") as stream:
                predictions = list(csv.DictReader(stream))
            self.assertEqual(len(predictions), 600)
            for name, key in (("baseline", "baseline_prediction"), ("logistic", "ml_prediction")):
                recomputed = q.metrics([int(r["defect"]) for r in predictions], [int(r[key]) for r in predictions])
                self.assertEqual(recomputed, result["test"][name])
                for key_count in ("tn", "fp", "fn", "tp"):
                    self.assertEqual(sum(m[name][key_count] for m in result["test_by_batch"].values()),
                                     recomputed[key_count])
            with (first / "failure_review.csv").open(newline="", encoding="utf-8") as stream:
                errors = list(csv.DictReader(stream))
            expected = sum(m["fp"] + m["fn"] for m in result["test"].values())
            self.assertEqual(len(errors), expected)
            self.assertEqual(json.loads((first / "metrics.json").read_text())["data_checks"]["rows"], 2400)
            self.assertIn("Synthetic results do not establish", (first / "report.html").read_text())


if __name__ == "__main__":
    unittest.main()

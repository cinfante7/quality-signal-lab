"""Tests tied to fictional QSL-001 specifications; no favorable-result assertions."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import quality_lab as q
import refinement as r


class RefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = q.generate(batches=15)
        cls.original = json.loads((r.ROOT / "artifacts" / "metrics.json").read_text())
        cls.model = cls.original["model"]

    def test_cs01_extended_validation(self):
        self.assertEqual(r.validate_extended(self.rows)["rows"], 3000)
        for batch in (0, 16, 13.5, True):
            with self.assertRaises(ValueError):
                r.validate_extended([{**self.rows[0], "batch": batch}])
        with self.assertRaises(ValueError):
            r.validate_extended([self.rows[0], self.rows[0]])
        with self.assertRaises(ValueError):
            r.validate_extended([{**self.rows[-1], "surface_score": float("nan")}])

    def test_cs02_mandatory_flags(self):
        # Even an extremely low predicted probability cannot clear a rule flag.
        model = {"means": [0, 0, 0], "scales": [1, 1, 1], "weights": [-40, 0, 0, 0]}
        for key, value in (("diameter_mm", 10.21), ("surface_score", 0.66), ("vibration_mm_s", 2.51)):
            row = dict(diameter_mm=10, surface_score=0.1, vibration_mm_s=1)
            row[key] = value
            self.assertEqual(r.hybrid(model, row, 0.95), 1)

    def test_cs03_capacity_selection(self):
        model = {"means": [0, 0.5, 0], "scales": [1, 1, 1], "weights": [0, 0, 4, 0]}
        rows = [dict(sample_id=str(i), batch=8, diameter_mm=10,
                     surface_score=s, vibration_mm_s=1, defect=int(s > 0.5))
                for i, s in enumerate((0.1, 0.2, 0.6, 0.64))]
        # These surfaces stay below the mandatory rule. Selected ML policy fits one slot.
        chosen, sweep = r.select_capacity_policy(model, rows)
        feasible = [c for c in sweep if all(b["capacity_ok"] for b in c["by_batch"].values())]
        self.assertEqual(chosen, min(feasible, key=lambda c: (c["aggregate"]["cost"], -c["threshold"])))
        self.assertEqual(len(sweep), 19)
        self.assertTrue(chosen["aggregate"]["capacity_ok"])
        # All mandatory flags makes any hybrid infeasible, regardless of threshold.
        chosen, _ = r.select_capacity_policy(model, [{**row, "diameter_mm": 10.3} for row in rows])
        self.assertIsNone(chosen)

    def test_cs04_gate(self):
        self.assertFalse(r.gate({}))
        self.assertTrue(r.gate({"8": {"capacity_ok": True, "recall_ok": True}}))
        self.assertFalse(r.gate({"8": {"capacity_ok": True, "recall_ok": True},
                                 "9": {"capacity_ok": True, "recall_ok": False}}))
        rows = [dict(defect=int(i < 5)) for i in range(10)]
        summary = r.summarize(rows, [1] * 4 + [0] * 6)
        self.assertEqual(summary["flag_rate"], 0.4)
        self.assertEqual(summary["recall"], 0.8)
        self.assertTrue(summary["capacity_ok"] and summary["recall_ok"])

    def test_cs05_reconcile(self):
        rows = [dict(defect=0), dict(defect=1), dict(defect=1)]
        summary = r.summarize(rows, [1, 0, 1])
        self.assertEqual([summary[k] for k in ("tn", "fp", "fn", "tp", "cost")], [0, 1, 1, 1, 6])
        errors = [{"error": "false alarm"}] * 3 + [{"error": "missed defect"}]
        pareto = r.pareto(errors)
        self.assertEqual([p["count"] for p in pareto], [3, 1])
        self.assertEqual([p["cumulative_percent"] for p in pareto], [0.75, 1])
        measurements = [dict(batch=1, diameter_mm=d, surface_score=0.1, vibration_mm_s=1)
                        for d in (9.9, 10.1)]
        v = r.variation(measurements)[0]
        self.assertEqual(v["diameter_mean_mm"], 10)
        self.assertAlmostEqual(v["diameter_sample_sd_mm"], 0.141421356237309, places=10)

    def test_cs06_split_and_frozen_model(self):
        groups = r.partitions(self.rows)
        self.assertEqual([len(g) for g in groups], [1400, 400, 600, 600])
        self.assertEqual(groups[0] + groups[1] + groups[2], q.generate())
        ids = [{row["sample_id"] for row in group} for group in groups]
        self.assertEqual(len(set.union(*ids)), sum(len(group) for group in groups))
        frozen = copy.deepcopy(self.model)
        selected, _ = r.select_capacity_policy(self.model, groups[1])
        for row in copy.deepcopy(groups[3]):
            row["defect"] = 1 - row["defect"]
            row["surface_score"] = 999
        self.assertEqual(r.select_capacity_policy(self.model, groups[1])[0], selected)
        self.assertEqual(self.model, frozen)

    def test_cs07_repeat_and_traceability(self):
        original_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (r.ROOT / "artifacts").iterdir() if p.is_file()}
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "first", Path(temp) / "second"
            a, b = r.run(first), r.run(second)
            self.assertEqual(a, b)
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            with (first / "new_holdout_predictions.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 600)
            for policy in a["new_holdout"]:
                counts = q.metrics([int(row["defect"]) for row in rows],
                                   [int(row[policy]) for row in rows])
                for key in counts:
                    self.assertEqual(counts[key], a["new_holdout"][policy]["aggregate"][key])
            errors = sum(a["new_holdout"]["capacity_hybrid"]["aggregate"][key] for key in ("fp", "fn"))
            self.assertEqual(sum(p["count"] for p in a["error_pareto"]), errors)
            self.assertEqual(set(a["spec_test_mapping"]), {f"CS{i:02d}" for i in range(1, 8)})
            suite = unittest.defaultTestLoader.discover(str(r.ROOT), pattern="test*.py")
            def flatten(tests):
                for test in tests:
                    if isinstance(test, unittest.TestSuite):
                        yield from flatten(test)
                    else:
                        yield ".".join(test.id().split(".")[-2:])
            available = set(flatten(suite))
            specification = (r.ROOT / "CUSTOMER-SPEC.md").read_text(encoding="utf-8")
            for requirement, tests in r.SPEC_TESTS.items():
                self.assertIn(requirement, specification)
                for test in tests:
                    self.assertIn(test, available)
                    self.assertIn(test, specification)
        self.assertEqual(original_hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in (r.ROOT / "artifacts").iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main()

"""Disclosed capacity-policy refinement; frozen model, new later-batch holdout."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import statistics

import quality_lab as q

ROOT = Path(__file__).resolve().parent
CAPACITY = 0.40
MIN_RECALL = 0.80
SPEC_TESTS = {
    "CS01": ["DataTests.test_r01_seed_and_schema", "DataTests.test_r02_reject_invalid_data",
             "RefinementTests.test_cs01_extended_validation"],
    "CS02": ["AlgorithmTests.test_r04_rule_boundaries", "RefinementTests.test_cs02_mandatory_flags"],
    "CS03": ["RefinementTests.test_cs03_capacity_selection"],
    "CS04": ["RefinementTests.test_cs04_gate"],
    "CS05": ["RefinementTests.test_cs05_reconcile"],
    "CS06": ["RefinementTests.test_cs06_split_and_frozen_model"],
    "CS07": ["PipelineTests.test_r08_outputs_reconcile_and_repeat",
             "RefinementTests.test_cs07_repeat_and_traceability"]
}


def validate_extended(rows):
    if any(type(r.get("batch")) is not int or not 1 <= r["batch"] <= 15 for r in rows):
        raise ValueError("Extended batch must be integer 1 through 15")
    # Reuse the original measurement/schema checks without changing original contract.
    return q.validate([{**r, "batch": min(r["batch"], 12)} for r in rows])


def partitions(rows):
    groups = [[r for r in rows if lo <= r["batch"] <= hi]
              for lo, hi in ((1, 7), (8, 9), (10, 12), (13, 15))]
    if any(not g or {r["defect"] for r in g} != {0, 1} for g in groups):
        raise ValueError("Each partition needs both classes")
    ids = [{r["sample_id"] for r in g} for g in groups]
    batches = [{r["batch"] for r in g} for g in groups]
    for i in range(4):
        for j in range(i):
            if ids[i] & ids[j] or batches[i] & batches[j]:
                raise ValueError("Partitions overlap")
    return groups


def hybrid(model, row, threshold):
    return int(q.baseline(row) or q.probability(model, row) >= threshold)


def summarize(rows, predicted):
    result = q.metrics([r["defect"] for r in rows], predicted)
    result["flag_rate"] = (result["tp"] + result["fp"]) / result["n"]
    result["capacity_ok"] = result["flag_rate"] <= CAPACITY
    result["recall_ok"] = result["recall"] >= MIN_RECALL
    return result


def gate(by_batch):
    return bool(by_batch) and all(m["capacity_ok"] and m["recall_ok"] for m in by_batch.values())


def evaluate(model, rows, policy, threshold=None):
    predictions = [q.baseline(r) if policy == "baseline" else
                   int(q.probability(model, r) >= threshold) if policy == "logistic" else
                   hybrid(model, r, threshold) for r in rows]
    by_batch = {}
    for batch in sorted({r["batch"] for r in rows}):
        indices = [i for i, r in enumerate(rows) if r["batch"] == batch]
        by_batch[str(batch)] = summarize([rows[i] for i in indices], [predictions[i] for i in indices])
    return {"aggregate": summarize(rows, predictions), "by_batch": by_batch,
            "requirements_pass": gate(by_batch)}, predictions


def select_capacity_policy(model, validation):
    """No test inputs: all validation batches must satisfy the review bound."""
    candidates = []
    for integer in range(5, 96, 5):
        threshold = integer / 100
        result, _ = evaluate(model, validation, "hybrid", threshold)
        candidates.append({"threshold": threshold, **result})
    feasible = [c for c in candidates if all(m["capacity_ok"] for m in c["by_batch"].values())]
    chosen = min(feasible, key=lambda c: (c["aggregate"]["cost"], -c["threshold"])) if feasible else None
    return chosen, candidates


def variation(rows):
    result = []
    for batch in sorted({r["batch"] for r in rows}):
        group = [r for r in rows if r["batch"] == batch]
        measurements = [r["diameter_mm"] for r in group]
        result.append({"batch": batch, "n": len(group),
                       "diameter_mean_mm": statistics.mean(measurements),
                       "diameter_sample_sd_mm": statistics.stdev(measurements),
                       "diameter_spec_excursions": sum(abs(v - 10) > 0.20 for v in measurements),
                       "any_measurement_flag": sum(q.baseline(r) for r in group)})
    return result


def pareto(errors):
    categories = ("false alarm", "missed defect")
    counts = [(kind, sum(r["error"] == kind for r in errors)) for kind in categories]
    counts.sort(key=lambda x: (-x[1], x[0]))
    total = len(errors)
    cumulative = 0
    result = []
    for category, count in counts:
        cumulative += count
        result.append({"category": category, "count": count,
                       "percent": count / total if total else 0.0,
                       "cumulative_percent": cumulative / total if total else 0.0})
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(output="refinement"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((ROOT / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    model = original["model"]  # Load coefficients, never refit or inspect new labels to train.
    original_bytes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted((ROOT / "artifacts").iterdir()) if p.is_file()}
    rows = q.generate(batches=15)
    checks = validate_extended(rows)
    train, validation, inspected, fresh = partitions(rows)
    # Freeze the capacity policy on validation before any new holdout scoring.
    chosen, sweep = select_capacity_policy(model, validation)
    threshold = chosen["threshold"] if chosen else 0.95
    policies = [("baseline", "baseline", None),
                ("original_cost_ml", "logistic", original["ml_threshold"]),
                ("capacity_hybrid", "hybrid", threshold)]
    final = {}
    prediction_columns = {}
    for name, policy, cutoff in policies:
        final[name], prediction_columns[name] = evaluate(model, fresh, policy, cutoff)
    validation_baseline, _ = evaluate(model, validation, "baseline")
    predictions = [dict(**r, ml_probability=q.probability(model, r),
                        **{name: values[i] for name, values in prediction_columns.items()})
                   for i, r in enumerate(fresh)]
    errors = [dict(**r, error="missed defect" if r["defect"] else "false alarm")
              for r in predictions if r["capacity_hybrid"] != r["defect"]]
    error_pareto = pareto(errors)
    batch_variation = variation(rows)
    verdict = "GO to further synthetic study" if chosen and chosen["requirements_pass"] and final["capacity_hybrid"]["requirements_pass"] else "NO-GO"
    result = {
        "revision": 2, "disclosure": "Policy refinement after original test inspection; no retraining",
        "seed": q.SEED, "original_artifact_sha256": original_bytes, "data_checks": checks,
        "split": {"train": list(range(1, 8)), "validation_exploratory": [8, 9],
                  "original_inspected_holdout": [10, 11, 12], "new_holdout": [13, 14, 15]},
        "model_frozen": model, "capacity": CAPACITY, "min_recall": MIN_RECALL,
        "hybrid_threshold": threshold, "capacity_feasible": chosen is not None,
        "validation_candidate": chosen, "validation_baseline": validation_baseline,
        "validation_sweep": sweep, "new_holdout": final, "verdict": verdict,
        "error_pareto": error_pareto, "spec_test_mapping": SPEC_TESTS}
    fields = q.FIELDS + ["ml_probability"] + [name for name, _, _ in policies]
    q.write_csv(output / "new_holdout_predictions.csv", predictions, fields)
    q.write_csv(output / "failure_review.csv", errors, fields + ["error"])
    q.write_csv(output / "variation.csv", batch_variation, list(batch_variation[0]))
    q.write_csv(output / "error_pareto.csv", error_pareto, list(error_pareto[0]))
    q.write_csv(output / "extended_synthetic_inspections.csv", rows, q.FIELDS)
    result["extended_data_sha256"] = hashlib.sha256((output / "extended_synthetic_inspections.csv").read_bytes()).hexdigest()
    write_json(output / "metrics.json", result)
    write_report(output, result, batch_variation)
    return result


def write_report(output, result, batch_variation):
    header = ["| Policy | TN | FP | FN | TP | Recall | Flags | Cost 5 FN + FP | Every-batch requirements |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name, evaluation in result["new_holdout"].items():
        m = evaluation["aggregate"]
        header.append(f'| {name} | {m["tn"]} | {m["fp"]} | {m["fn"]} | {m["tp"]} | {m["recall"]:.1%} | {m["flag_rate"]:.1%} | {m["cost"]} | {evaluation["requirements_pass"]} |')
    val_table = ["| Hybrid threshold | Validation recall | Validation flags | Cost | Every-batch capacity | Every-batch full requirements |",
                 "|---|---:|---:|---:|---|---|"]
    for c in result["validation_sweep"]:
        m = c["aggregate"]
        val_table.append(f'| {c["threshold"]:.2f} | {m["recall"]:.1%} | {m["flag_rate"]:.1%} | {m["cost"]} | {all(b["capacity_ok"] for b in c["by_batch"].values())} | {c["requirements_pass"]} |')
    variation_table = ["| Batch | Diameter mean mm | Sample SD mm | Diameter excursions / 200 | Any rule flags / 200 |",
                       "|---|---:|---:|---:|---:|"]
    for r in batch_variation:
        variation_table.append(f'| {r["batch"]} | {r["diameter_mean_mm"]:.4f} | {r["diameter_sample_sd_mm"]:.4f} | {r["diameter_spec_excursions"]} | {r["any_measurement_flag"]} |')
    report = f"""# Quality Signal Lab — capacity review, revision 2

**{result['verdict']}** under fictional QSL-001 requirements.
New AI-assisted portfolio exercise, October 2026; no real customer or factory claims.

## Disclosure and freeze
This revision followed inspection of the first 600-item test (batches 10–12).
The first report and release ZIP remain intact. Model coefficients, scaling and
rule limits were frozen. Existing validation batches 8–9 were reused for
exploratory policy comparison; this is a disclosed refinement, not the original
pre-registered experiment. New batches 13–15 (600 items) were untouched until
the validation-only capacity threshold was selected. They continue the same
synthetic drift and logistic label mechanism, so they are not an independent
factory or a new failure type. No threshold was adjusted after new holdout review.

## Customer interpretation and operational gate
Fictional capacity: at most 80 of 200 items per batch (40%), with latent-defect
recall ≥80% in every batch. Mandatory measurement flags cannot be cleared by ML.
Hybrid = fixed rule OR model probability ≥ threshold. Select lowest validation
5 FN + FP cost among candidates meeting capacity in every validation batch.
Ties prefer higher threshold. Selected hybrid threshold: {result['hybrid_threshold']:.2f}.
Validation requirement gate: {bool(result['validation_candidate'] and result['validation_candidate']['requirements_pass'])}.
If the mandatory rule alone exceeds capacity, a supplementary model cannot fix
that conflict; escalate the specification and process question.

## New untouched holdout — frozen policies
""" + "\n".join(header) + """

The cost-only ML is retained as context; it does not preserve mandatory flags.
It is not eligible to replace the specification-derived baseline.
The original baseline is unchanged and never optimized against label outcomes.
Even a lower hypothetical error cost does not authorize operation when review
capacity or recall requirements fail. A NO-GO result is a useful engineering
finding: queue load, defect misses and customer goals cannot be hidden by accuracy.

## Validation-only policy comparison
The entire grid below uses batches 8–9 only. Aggregate percentages aid comparison;
the gate uses each batch. Full per-batch values are in metrics.json.

""" + "\n".join(val_table) + """

## Failure review and error Pareto
failure_review.csv contains every capacity-hybrid error. error_pareto.csv and
error_pareto.svg rank mutually exclusive false alarms and missed defects;
one item contributes to at most one error category for this one policy.
This is an error-workload Pareto, not causal defect categories, independent model
errors pooled together, or evidence for an 80/20 law. Sorting errors does not
establish a root cause. Confirm measurement methods and label adjudication first.

## Basic variation review
""" + "\n".join(variation_table) + """

Mean and sample SD (denominator n−1) describe generated diameter measurements.
The intentionally changing mean violates a stable-process interpretation.
Limits are invented specification limits, not statistical control limits.
No Cp/Cpk, gauge R&R, Six Sigma level or certified improvement is claimed.

## Limitations and next priority
Labels include Bernoulli uncertainty, so measurements cannot determine every
outcome. The logistic label mechanism favors the selected model family. Vibration
and surface are generic numeric surrogates; no optical or electronics hardware,
image detection, real machine integration or physical process knowledge is shown.
A human must resolve specification/label meaning, acceptable escape severity,
capacity and measurement-system uncertainty before collecting independent real lots.
See CUSTOMER-SPEC.md, PROCESS-MAP.md and ISSUE-LOG.md for interpretation and priority.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    bars = []
    maximum = max((r["count"] for r in result["error_pareto"]), default=1) or 1
    for index, r in enumerate(result["error_pareto"]):
        y = 65 + index * 75
        bars.append(f'<text x="20" y="{y}" font-size="16">{html.escape(r["category"])}</text><rect x="165" y="{y-22}" width="{r["count"] / maximum * 340:.1f}" height="30" fill="#23675e"/><text x="520" y="{y}" font-size="16">{r["count"]} ({r["cumulative_percent"]:.1%} cumulative)</text>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 200" role="img" aria-label="Pareto of capacity-hybrid prediction errors"><rect width="780" height="200" fill="white"/><text x="20" y="25" font-size="18">Hybrid error workload — new holdout</text>' + "".join(bars) + '</svg>'
    (output / "error_pareto.svg").write_text(svg, encoding="utf-8")
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quality Signal Lab | Capacity review</title><style>body{font:16px/1.6 system-ui;background:#eef2f5;color:#162b38;max-width:1100px;margin:auto;padding:28px}pre{white-space:pre-wrap;background:white;padding:24px}img{width:100%}a{color:#155d78}</style><h1>Quality Signal Lab: capacity review</h1><p><strong>' + result["verdict"] + '</strong> • Fictional requirements • October 2026</p><img src="error_pareto.svg" alt="Prediction error Pareto"><p><a href="metrics.json">Full metrics</a> · <a href="failure_review.csv">All errors</a> · <a href="variation.csv">Batch variation</a></p><pre>' + html.escape(report) + '</pre></html>'
    (output / "report.html").write_text(document, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="refinement")
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({"verdict": result["verdict"], "hybrid_threshold": result["hybrid_threshold"],
                      "new_holdout": result["new_holdout"]}, indent=2))

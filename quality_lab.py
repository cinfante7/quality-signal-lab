"""Synthetic quality inspection experiment. Python standard library only."""
import argparse
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import platform
import random

SEED = 20261011
FIELDS = ["sample_id", "batch", "diameter_mm", "surface_score", "vibration_mm_s", "defect"]
FEATURES = ["diameter_mm", "surface_score", "vibration_mm_s"]
THRESHOLDS = (0.20, 0.65, 2.50)


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


def generate(seed=SEED, batches=12, per_batch=200):
    """Independent noise plus batch drift; latent quality has imperfect observability."""
    rng = random.Random(seed)
    rows = []
    for batch in range(1, batches + 1):
        drift = (batch - 1) * 0.012
        for index in range(per_batch):
            diameter = 10 + rng.gauss(drift, 0.115)
            surface = min(1.0, max(0.0, rng.gauss(0.31 + drift * 0.6, 0.15)))
            vibration = max(0.0, rng.gauss(1.55 + drift * 2, 0.43))
            # No label is exposed as an input. Noise represents unmeasured factors.
            risk = -4.1 + 7 * abs(diameter - 10) + 3.0 * surface + 0.8 * vibration
            defect = int(rng.random() < sigmoid(risk))
            rows.append(dict(sample_id=f"B{batch:02d}-{index:03d}", batch=batch,
                             diameter_mm=round(diameter, 5), surface_score=round(surface, 5),
                             vibration_mm_s=round(vibration, 5), defect=defect))
    return rows


def validate(rows):
    if not rows:
        raise ValueError("Empty inspection data")
    ids = set()
    for row in rows:
        if set(row) != set(FIELDS):
            raise ValueError("Unexpected data schema")
        if not isinstance(row["sample_id"], str) or not row["sample_id"]:
            raise ValueError("Invalid sample identifier")
        if row["sample_id"] in ids:
            raise ValueError("Duplicate sample identifier")
        ids.add(row["sample_id"])
        if type(row["batch"]) is not int or not 1 <= row["batch"] <= 12:
            raise ValueError("Batch must be an integer from 1 to 12")
        if type(row["defect"]) is not int or row["defect"] not in (0, 1):
            raise ValueError("Defect must be binary")
        for feature in FEATURES:
            if not isinstance(row[feature], (int, float)) or not math.isfinite(row[feature]):
                raise ValueError("Non-finite measurement")
        if not 9 <= row["diameter_mm"] <= 11 or not 0 <= row["surface_score"] <= 1 or not 0 <= row["vibration_mm_s"] <= 10:
            raise ValueError("Measurement outside synthetic domain")
    return {"rows": len(rows), "unique_ids": len(ids), "finite": True, "schema": FIELDS}


def split(rows):
    """Chronological, whole-batch split. IDs and batches never enter the model."""
    train = [r for r in rows if r["batch"] <= 7]
    validation = [r for r in rows if 8 <= r["batch"] <= 9]
    test = [r for r in rows if r["batch"] >= 10]
    for group in (train, validation, test):
        if not group or set(r["defect"] for r in group) != {0, 1}:
            raise ValueError("Every partition needs both classes")
    assert not ({r["sample_id"] for r in train} & {r["sample_id"] for r in test})
    return train, validation, test


def vector(row):
    # Engineering transform chosen before evaluation; symmetric nominal deviation.
    return [abs(row["diameter_mm"] - 10), row["surface_score"], row["vibration_mm_s"]]


def baseline(row):
    deviation, surface, vibration = vector(row)
    return int(deviation > THRESHOLDS[0] or surface > THRESHOLDS[1] or vibration > THRESHOLDS[2])


def fit(rows, epochs=700, rate=0.1, penalty=0.01):
    """Full-batch gradient descent, unweighted L2 logistic loss, train-only scaling."""
    xs = [vector(r) for r in rows]
    means = [sum(x[j] for x in xs) / len(xs) for j in range(3)]
    scales = [math.sqrt(sum((x[j] - means[j]) ** 2 for x in xs) / len(xs)) or 1 for j in range(3)]
    design = [[1] + [(x[j] - means[j]) / scales[j] for j in range(3)] for x in xs]
    weights = [0.0] * 4
    for _ in range(epochs):
        gradient = [0.0] * 4
        for x, row in zip(design, rows):
            error = sigmoid(sum(w * v for w, v in zip(weights, x))) - row["defect"]
            for j in range(4):
                gradient[j] += error * x[j]
        weights = [w - rate * (gradient[j] / len(rows) + (penalty * w if j else 0))
                   for j, w in enumerate(weights)]
    return dict(means=means, scales=scales, weights=weights,
                epochs=epochs, learning_rate=rate, l2_penalty=penalty)


def probability(model, row):
    x = [1] + [(v - m) / s for v, m, s in zip(vector(row), model["means"], model["scales"])]
    return sigmoid(sum(w * v for w, v in zip(model["weights"], x)))


def metrics(actual, predicted):
    if len(actual) != len(predicted) or not actual:
        raise ValueError("Nonempty, aligned predictions required")
    if any(type(v) is not int or v not in (0, 1) for v in actual + predicted):
        raise ValueError("Binary labels required")
    tn = sum(a == 0 and p == 0 for a, p in zip(actual, predicted))
    fp = sum(a == 0 and p == 1 for a, p in zip(actual, predicted))
    fn = sum(a == 1 and p == 0 for a, p in zip(actual, predicted))
    tp = sum(a == 1 and p == 1 for a, p in zip(actual, predicted))
    return dict(tn=tn, fp=fp, fn=fn, tp=tp, n=len(actual),
                precision=tp / (tp + fp) if tp + fp else 0.0,
                recall=tp / (tp + fn) if tp + fn else 0.0,
                accuracy=(tp + tn) / len(actual), cost=5 * fn + fp,
                defect_rate=(tp + fn) / len(actual))


def select_threshold(model, rows):
    """Validation-only policy: each missed defect costs 5, false alarm costs 1."""
    scores = [probability(model, r) for r in rows]
    actual = [r["defect"] for r in rows]
    candidates = []
    for integer in range(5, 96, 5):
        threshold = integer / 100
        result = metrics(actual, [int(p >= threshold) for p in scores])
        candidates.append(dict(threshold=threshold, **result))
    chosen = min(candidates, key=lambda r: (r["cost"], -r["threshold"]))
    return chosen["threshold"], candidates


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = generate()
    checks = validate(rows)
    train, validation, test = split(rows)
    model = fit(train)
    threshold, sweep = select_threshold(model, validation)
    predictions = [dict(**r, baseline_prediction=baseline(r),
                        ml_probability=probability(model, r),
                        ml_prediction=int(probability(model, r) >= threshold)) for r in test]
    actual = [r["defect"] for r in test]
    result = {
        "seed": SEED, "python_version": platform.python_version(),
        "split": {"train_batches": [1, 7], "validation_batches": [8, 9], "test_batches": [10, 12],
                  "train_n": len(train), "validation_n": len(validation), "test_n": len(test)},
        "data_checks": checks, "ml_threshold": threshold, "model": model,
        "cost_assumption": {"false_negative": 5, "false_positive": 1},
        "test": {"baseline": metrics(actual, [r["baseline_prediction"] for r in predictions]),
                 "logistic": metrics(actual, [r["ml_prediction"] for r in predictions])},
        "test_by_batch": {}, "validation_sweep": sweep}
    for batch in (10, 11, 12):
        group = [r for r in predictions if r["batch"] == batch]
        result["test_by_batch"][str(batch)] = {
            name: metrics([r["defect"] for r in group], [r[key] for r in group])
            for name, key in (("baseline", "baseline_prediction"), ("logistic", "ml_prediction"))}
    write_csv(output / "synthetic_inspections.csv", rows, FIELDS)
    result["data_sha256"] = hashlib.sha256((output / "synthetic_inspections.csv").read_bytes()).hexdigest()
    prediction_fields = FIELDS + ["baseline_prediction", "ml_probability", "ml_prediction"]
    write_csv(output / "test_predictions.csv", predictions, prediction_fields)
    errors = [dict(**r, model=name, error="missed defect" if r["defect"] else "false alarm")
              for r in predictions for name, key in (("baseline", "baseline_prediction"), ("logistic", "ml_prediction"))
              if r["defect"] != r[key]]
    write_csv(output / "failure_review.csv", errors, prediction_fields + ["model", "error"])
    (output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    table = ["| Method | TN | FP | FN | TP | Precision | Recall | Cost (5 FN + FP) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, m in result["test"].items():
        table.append(f'| {name} | {m["tn"]} | {m["fp"]} | {m["fn"]} | {m["tp"]} | {m["precision"]:.3f} | {m["recall"]:.3f} | {m["cost"]} |')
    b, ml = result["test"]["baseline"], result["test"]["logistic"]
    examples = ["| Model | Error | Sample | Diameter mm | Surface | Vibration mm/s | ML probability |",
                "|---|---|---|---:|---:|---:|---:|"]
    for name in ("baseline", "logistic"):
        for kind in ("missed defect", "false alarm"):
            group = [r for r in errors if r["model"] == name and r["error"] == kind][:2]
            for r in group:
                examples.append(f'| {name} | {kind} | {r["sample_id"]} | {r["diameter_mm"]:.5f} | {r["surface_score"]:.5f} | {r["vibration_mm_s"]:.5f} | {r["ml_probability"]:.3f} |')
    report = f"""# Quality Signal Lab — evaluation and failure review

New AI-assisted portfolio demonstration for Christopher Infante, created October 2026.
Synthetic data only; no real manufacturing performance claim.

## Frozen experiment
Seed {SEED}; 2,400 samples across 12 ordered batches. Train: batches 1–7 (1,400);
validation: 8–9 (400); final test: 10–12 (600). Scaling and model weights fit on
training only. A 19-point threshold grid is selected only on validation, minimizing
5 × missed defects + false alarms; ties prefer the larger threshold. Selected: {threshold:.2f}.
Model settings and engineering transforms were fixed before inspecting test results.

## Held-out results
Defects in test: {b['tp'] + b['fn']} / 600 ({b['defect_rate']:.1%}).

""" + "\n".join(table) + f"""

Confusion counts use actual defect as the positive class. Cost is an illustrative
relative penalty, not dollars or a verified business loss. Accuracy alone is not
the decision criterion. The rule flags {(b['tp'] + b['fp']) / 600:.1%} of items;
ML flags {(ml['tp'] + ml['fp']) / 600:.1%}. At the same assumed costs, flagging every
item would cost {b['tn'] + b['fp']}, while accepting every item would cost {5 * (b['fn'] + b['tp'])}.
ML's small improvement over flagging everything underscores the review burden.
With these frozen predictions, equal FN/FP costs favor the rule
({b['fn'] + b['fp']} errors versus {ml['fn'] + ml['fp']}); 5:1 costs favor ML.
This is post-evaluation sensitivity analysis, not retuning.

## Failure review
The fixed rule misses {b['fn']} defects and flags {b['fp']} acceptable samples.
The logistic model misses {ml['fn']} defects and flags {ml['fp']} acceptable samples.
The test cost difference (ML minus rule) is {ml['cost'] - b['cost']}.
Every error, its measurements, batch, label and probability is in failure_review.csv;
all 600 samples are in test_predictions.csv. Per-batch counts are in metrics.json.
First two cases by sample order in each error category (no cherry-picking):

{chr(10).join(examples)}

The rule can miss moderate combined signals because each individual measurement
remains under its threshold. A low model threshold can catch those signals while
also producing many false alarms. Neither predictor can recover the unobserved
random component of the synthetic label. These are hypotheses from the generating
mechanism, not verified root causes in a factory. Review cases against process
history, measurement-system repeatability and independent adjudicated labels before
taking action. In production, hold suspected items for human inspection rather
than allowing automatic release.

## Decision and next experiment
Compare the actual counts and the assumed 5:1 tradeoff before choosing a policy.
Do not adopt ML solely because its assumed cost is lower. Quantify real false-alarm
capacity and escape severity; repeat on independent lots, assess measurement error,
and test threshold sensitivity. The validation sweep is included for inspection.
No repeated test-driven model tuning was performed.

## Limits
One seeded synthetic world, noisy invented labels, simple gradual drift, and three
scalar measurements. This is not a machine-vision system or a validated inspection
instrument. No image defects, gauge R&R, real acceptance specification, correlated
lot failures, or real class prevalence are established. The same broad risk formula
defines every batch; this makes generalization easier than unseen factory failure
modes. The label mechanism resembles the selected model; model advantage may
reflect that assumption. Batch-level rates should be reviewed even when aggregate
metrics look favorable. No confidence interval or manufacturing certification is claimed.

## Reproducibility
Data SHA-256: {result['data_sha256']}
Python: {platform.python_version()}; no third-party packages.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    render_html(output / "report.html", result, report)
    return result


def render_html(path, result, report):
    cards = ""
    for name, m in result["test"].items():
        cells = "".join(f"<td>{v}</td>" for v in (m["tn"], m["fp"], m["fn"], m["tp"]))
        cards += f"""<section><h2>{html.escape(name)}</h2>
<p>Recall {m['recall']:.1%} · Precision {m['precision']:.1%} · Cost {m['cost']}</p>
<table><caption>Actual rows / predicted columns</caption><tr><th></th><th>Acceptable</th><th>Defect</th></tr>
<tr><th>Acceptable</th><td>{m['tn']}</td><td>{m['fp']}</td></tr>
<tr><th>Defect</th><td>{m['fn']}</td><td>{m['tp']}</td></tr></table></section>"""
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quality Signal Lab | Evaluation</title><style>
body{{font:16px/1.6 system-ui,sans-serif;margin:0;background:#eef2f5;color:#162b38}}
main{{max-width:1000px;margin:auto;padding:40px 24px}}h1{{font-size:42px;margin:8px 0}}
.tag{{color:#23675e;font-weight:700}}.cards{{display:flex;gap:20px;flex-wrap:wrap}}
section{{background:white;padding:24px;flex:1;min-width:250px;border-top:4px solid #23675e}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;border:1px solid #cbd5db;text-align:center}}
pre{{white-space:pre-wrap;background:white;padding:24px;font:14px/1.7 ui-monospace,monospace}}
a{{color:#155d78}}@media print{{body{{background:white}}main{{padding:0}}}}
</style><main><div class="tag">ENGINEERING + APPLIED ML • OCTOBER 2026</div>
<h1>Quality Signal Lab</h1><p>Synthetic inspection · batch holdout · traceable failure review</p>
<p><strong>Portfolio demonstration:</strong> AI-assisted, newly created. Synthetic results do not establish real manufacturing performance.</p>
<div class="cards">{cards}</div><p><a href="failure_review.csv">All errors (CSV)</a> ·
<a href="test_predictions.csv">Held-out predictions</a> · <a href="metrics.json">Metrics and threshold sweep</a></p>
<pre>{html.escape(report)}</pre></main></html>"""
    path.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts", help="Generated output directory")
    args = parser.parse_args()
    results = run(args.output)
    print(json.dumps({"threshold": results["ml_threshold"], "test": results["test"]}, indent=2))

# Requirements and verification

New AI-assisted portfolio project, October 2026. All acceptance specifications below
are invented for this exercise. They are not a company's inspection specifications.

## Problem and intended use

A quality engineer must compare a transparent screening rule with a trained risk
model, examining missed defects and false alarms on later, unseen batches.
The output supports a human investigation of inspection policy; it does not release
parts, control equipment or establish process capability.

## Synthetic measurement contract

- Unit of observation: one independent synthetic item, 200 per ordered batch.
- Diameter: nominal 10 mm, Gaussian standard deviation 0.115 mm.
- Surface score: unitless surrogate in [0,1], Gaussian mean 0.31, SD 0.15, clipped.
- Vibration: mm/s surrogate, Gaussian mean 1.55, SD 0.43, lower-clipped at zero.
- Batch drift: 0.012 per batch offset, added to diameter; 0.6 times offset to
  surface mean; 2 times offset to vibration mean. Time is represented by batch order.
- Label: Bernoulli draw with probability sigmoid(-4.1 + 7 |diameter - 10| +
  3 surface + 0.8 vibration). Labels are invented latent quality outcomes,
  not deterministic measurement-limit violations. Rounding to five decimals
  follows label generation. There is no physical simulator.
- Rule: flag if |diameter - 10| > 0.20 mm OR surface > 0.65 OR vibration > 2.50 mm/s.
  Exactly equal to a threshold is acceptable. These limits are fixed before
  evaluation and intentionally serve a different purpose from a latent risk score.
- Model: logistic classifier on absolute diameter deviation, surface, vibration.
  Batch and sample ID are excluded. Train-only population mean/SD scaling.
  Full-batch gradient descent: 700 epochs, rate 0.1, L2 0.01 on slopes only.
  No class weighting, external pretrained model or API.
- Decision policy: 19 thresholds 0.05 to 0.95; minimize validation 5 FN + FP.
  These relative costs are hypothetical. Hyperparameters and rule are fixed.

## Traceability matrix

| ID | Requirement / acceptance criterion | Verification |
|---|---|---|
| R01 | Seeded generation; 2,400 unique rows, documented schema | DataTests.test_r01_seed_and_schema |
| R02 | Reject empty data, duplicate IDs, wrong schema, invalid labels/batches, non-finite or out-of-domain measurements | DataTests.test_r02_reject_invalid_data |
| R03 | Whole-batch train 1–7, validation 8–9, test 10–12; both labels present, no overlap | DataTests.test_r03_batch_isolation |
| R04 | Fixed OR rule with explicit strict measurement boundaries | AlgorithmTests.test_r04_rule_boundaries |
| R05 | Classifier learns a separable fixture; scaling fits training; identifiers excluded | AlgorithmTests.test_r05_training_learns_and_ignores_identifiers |
| R06 | Threshold chosen on validation costs only; held-out changes do not alter selection or training state | AlgorithmTests.test_r06_threshold_minimizes_validation_cost |
| R07 | Confusion matrix and cost arithmetic correct, zero denominators handled | AlgorithmTests.test_r07_confusion_counts_and_zero_denominators |
| R08 | Pipeline outputs reproducible bytes; CSV errors and per-batch confusion counts reconcile | PipelineTests.test_r08_outputs_reconcile_and_repeat |
| R09 | Disclose synthetic and AI-assisted provenance; avoid historical or real-performance claims | README, report, manual source review |

Tests use the Python standard library unittest runner. R06 verifies the dependency
boundary in the public function API; inspect run() to verify only train is passed
to fit and only validation to threshold selection. R08 runs the complete pipeline
twice in temporary directories. It does not demand that ML outperform the rule.

## Review risks

Label-generation assumptions favor additive logistic risk modeling. There is one
seed, gradual drift and independent item noise; no unseen failure mode or true lot
dependence. A later real project needs adjudicated labels, measurement-system
analysis, leakage review, process expertise, independent lots and cost sensitivity.
The generated report and failures are the evidence, not a production qualification.

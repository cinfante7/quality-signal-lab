# Fictional customer specification — QSL-001 revision 2

**Entirely fictional training scenario.** Created after the original holdout was
reviewed, October 2026. No actual customer, hardware or manufacturing outcome.

The fictional customer supplies 200 scalar-measurement records per inspection
batch. The engineer must return a traceable batch summary and a disposition
recommendation before the next hypothetical batch arrives. No real turnaround
contract is asserted. Invalid data takes priority over model scoring.

| ID | Customer statement | Engineering interpretation | Verification |
|---|---|---|---|
| CS01 | Identify every item and retain its batch | Unique nonempty sample ID; original batch retained; reject malformed schema and invalid measurements | DataTests.test_r01_seed_and_schema; DataTests.test_r02_reject_invalid_data; RefinementTests.test_cs01_extended_validation |
| CS02 | Nominal diameter 10.00 mm, tolerance ±0.20 mm; surface ≤0.65; vibration ≤2.50 mm/s | Flag strict excursions beyond any limit. A model must never clear a limit violation. These invented limits define measurement flags, not the noisy latent-defect labels. | AlgorithmTests.test_r04_rule_boundaries; RefinementTests.test_cs02_mandatory_flags |
| CS03 | Secondary inspection capacity is 80 items per 200-item batch | At most 40% flags in each validation batch; evaluate the same bound per final batch. Include all flags, not just false alarms. Capacity is an admission criterion, not an assertion that unflagged items are safe. | RefinementTests.test_cs03_capacity_selection; refinement/metrics.json |
| CS04 | Catch at least 80% of independently adjudicated latent defects | Recall ≥0.80 in every validation batch and every new holdout batch; if unmet, report NO-GO. Synthetic labels stand in for adjudication only in this exercise. | RefinementTests.test_cs04_gate; refinement/report.md |
| CS05 | Explain results and investigate failures | Confusion counts, every prediction and error, per-batch checks, mutually exclusive error Pareto, measurement variation summary | RefinementTests.test_cs05_reconcile; refinement/failure_review.csv; refinement/variation.csv |
| CS06 | Keep later batches out of training and policy selection | Original train 1–7 and validation 8–9; original inspected test 10–12 preserved; untouched 13–15 used only after policy freeze | RefinementTests.test_cs06_split_and_frozen_model; REFINEMENT-PLAN.md |
| CS07 | Provide a repeatable, timely first release with explicit priorities | No third-party dependencies; two documented commands; byte-identical pipeline outputs, 1-hour hypothetical triage priority over optional visuals | PipelineTests.test_r08_outputs_reconcile_and_repeat; RefinementTests.test_cs07_repeat_and_traceability; ISSUE-LOG.md |

## Clarifications a quality engineer would seek

Do diameter limits reflect functional fit or a measurement method? Is the surface
score calibrated to an actual defect criterion? Is vibration measured on each item
or a machine? Which excursions require quarantine versus remeasurement? Who
adjudicates latent defects, and how does label uncertainty affect the recall goal?
What is the real capacity per shift, escape severity and acceptable false-alarm cost?
These remain unresolved real-world questions, explicitly invented here.

The baseline is specification-derived and fixed, not chosen to make ML look good.
It screens measurement excursions; ML estimates an invented latent outcome.
This purpose mismatch prevents interpreting their comparison as replacement
qualification. The hybrid preserves the specification rule.

Academic computer-vision learning can motivate interest in inspection analytics.
This scalar exercise does not demonstrate optical-system calibration, electronics
troubleshooting, factory experience, hands-on vision hardware or Six Sigma
certification.

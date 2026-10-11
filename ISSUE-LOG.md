# Prioritized issue log — QSL-001 revision 2

All roles and response targets below are hypothetical. Status describes this
local analytical exercise, not action in a real factory. Open qualification issues
are intentionally not marked solved merely because software tests pass.

| ID | Priority / response target | Evidence and implication | Required next action / hypothetical owner | Status |
|---|---|---|---|---|
| QI01 | P0 before any operational use | No policy satisfies CS03 capacity plus CS04 recall in every validation batch. Refined holdout is also NO-GO. Hybrid threshold 0.40 flags 116, 115, 127 items in batches 13–15 versus capacity 80; recall 78.6%, 75.6%, 79.8%. | Quality lead: reject deployment recommendation; resolve capacity/escape goals and collect independent evidence. Do not retune inspected holdouts. | NO-GO documented; qualification open |
| QI02 | P0 before score/disposition | Measurement specification and latent label mean different things. A false alarm against a synthetic latent label can still violate a mandatory measurement limit. | Customer/quality engineer: clarify functional criteria, measurement method and human disposition authority. Fixed rule remains mandatory (CS02). | Interpretation disclosed; real clarification open |
| QI03 | P1 first hypothetical shift | Mandatory rule alone flags 88, 80, 86 items on new batches; two exceed capacity. Diameter mean drifts from 10.0026 to 10.1696 mm across 15 generated batches. A supplementary classifier cannot remove this burden. | Process engineer: investigate invented mean-shift scenario and repeatability; consider process correction only after actual measurement review. | Descriptive variation evidence provided; no physical correction claimed |
| QI04 | P1 before experiment acceptance | Empty/invalid/duplicate data or leaking batch IDs would invalidate conclusions. CS01 and CS06 tests reject invalid measurements; identifiers excluded; batch splits isolated; frozen artifact hashes retained. | Analyst: run verification, inspect split contracts and evidence hashes. | Software checks passed |
| QI05 | P1 before adopting ML | Original cost-only ML flags 554/600 new items, with 297 false alarms. Hybrid has 152 false alarms and 58 missed defects. Pareto: false alarms 72.4% of 210 hybrid errors, then misses 27.6%; this ranks error workload, not root causes. | Inspection lead: quantify actual review time and escape severity; validate label adjudication. | Burden quantified; real costs/capacity unresolved |
| QI06 | P2 next independent study | One logistic-friendly generator and known gradual drift; no image/optical/electronics hardware, unseen failure mode or true lot dependence. No real throughput or measurement-system study. | Analyst/process mentor: design independent labeled lots, real measurement validation and failure-mode challenge with domain support. | Limitation explicit; no credentials claimed |
| QI07 | P2 after technical review | Existing supported GitHub CLI authenticated as cinfante7; parent cleared creation after cancelling manual request. Exact target returned 404, then new private repository metadata verified. | Retain both releases and verify upload identities. Public sharing remains separately pending. | Private target created; see PUBLICATION.md |

## Prioritization rationale

Protect valid data and safe interpretation first, then resolve capacity and
specification conflicts, then expand evidence. Cosmetic visuals and publication
do not outrank failing acceptance requirements. The local software suite finishes
in seconds; no factory response-time promise is inferred from that.

Evidence: CUSTOMER-SPEC.md, PROCESS-MAP.md, refinement/report.md,
refinement/metrics.json, refinement/variation.csv, refinement/error_pareto.csv,
refinement/failure_review.csv and verification-v2.json.

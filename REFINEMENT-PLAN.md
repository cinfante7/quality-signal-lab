# Refinement plan — frozen before inspecting batches 13–15

October 11, 2026. Revision 2 follows inspection of the original batches 10–12.
Original artifacts and release ZIP are preserved. This is a disclosed refinement,
not a claim that these new requirements preceded the first release.

Model coefficients, preprocessing, label generator and inspection-rule limits
remain frozen. Reuse batches 8–9 for exploratory policy selection; they are no
longer a pristine experiment design resource. Do not tune on original test batches
10–12. Extend the same seeded generator to batches 13–15 and inspect that new
600-item holdout only after the policy is frozen. Later batches continue the known
drift; this is not an independent factory or unseen failure mechanism.

Fictional capacity: at most 40% of items (80 of 200) may enter secondary review.
Target latent-defect recall: at least 80%. These are invented exercise requirements.
Measurement-specification flags are mandatory and cannot be cleared by ML.
Select an optional supplementary hybrid threshold on validation only:
baseline OR ML, thresholds 0.05–0.95 in 0.05 steps, minimum 5 FN + FP among
policies satisfying capacity; ties prefer larger threshold.
If no policy satisfies both capacity and recall on validation, mark NO-GO.
Evaluate the capacity-selected candidate on the untouched holdout for transparency,
even if it was already rejected; no post-test adjustment or retraining.

Compare standalone baseline, original cost-only ML threshold, and capacity-selected
hybrid. Keep all validation candidates. Show batch diameter mean, sample SD and
measurement-specification fraction; do not claim Cp/Cpk or control-chart validity.
Pareto categories are mutually exclusive hybrid prediction errors, not root causes.

Acceptance: deterministic bytes, extended split separation, metric reconciliation,
capacity selection boundary, mandatory-rule preservation and specification/test
traceability. Do not demand a favorable ML result.

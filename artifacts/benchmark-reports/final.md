# REWIND golden benchmark — E9.1

- **Cases:** `case_02` (`ESTOP_OCCLUDED`), `case_06` (`BLOCKED_AMBIGUOUS`), held out since E1.3, opened once
- **Run:** 2026-09-14 19:18–19:20 +0530, Apple M4, MPS; log `artifacts/golden-run-2026-09-14.log`
- **Pre-registration:** `docs/experiments/EXP-0010-golden-benchmark.md`, committed `03a0732` before the run
- **Configuration:** exactly as signed off at Gates 1–5; nothing changed between pre-registration and run
- **Diagnosis of every failure:** EXP-0010, "Failure analysis"

These are the held-out numbers. A later fix is measured beside them and labelled
post-golden; it never replaces them.

## Charter §6 floors

| Metric | Floor | case_02 | case_06 | Pooled | Verdict |
|---|---|---|---|---|---|
| Detection recall, person | ≥ 0.95 | 0.065 | — (no person) | 0.065 | **FAIL** |
| Detection precision, person | ≥ 0.95 | 0.875 | — | 0.875 | **FAIL** |
| Detection recall, robot | ≥ 0.95 | 0.991 | — (no robot) | 0.991 | PASS |
| Detection precision, robot | ≥ 0.95 | 0.998 | — | 0.998 | PASS |
| ID switches, worst camera | ≤ 2 | 2 (CAM_B) | 0 | 2 | PASS |
| Zone-event precision, real pipeline | ≥ 0.85 | 0.27 | 0.55 | 0.38 | **FAIL** |
| Zone-event recall, real pipeline | ≥ 0.90 | 0.80 | 0.43 | 0.53 | **FAIL** |
| Event timing error, max | ≤ 0.5 s | 0.25 s | 0.40 s | 0.40 s | PASS |
| Cross-camera false-link rate | ≤ 0.05 | 0.50 (2 of 4) | 0.00 (0 of 4) | 0.25 | **FAIL** |
| Cross-camera recall | ≥ 0.65 | 0.18 | 0.67 | 0.35 | **FAIL** |
| Evidence coverage, every report | ≥ 0.95 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 | PASS |
| Unsupported-claim rate, every report | 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 | PASS |
| Gap recall | ≥ 0.90 | 1.00 / 1.00 | 1.00 / 0.995 | ≥ 0.995 | PASS |
| Cause top-3, detections | 1.00 | missed | missed | 3 of 5 with tune | **FAIL** |
| Cause top-1, detections, five incidents | ≥ 0.67 | missed | missed | 0.60 (3 of 5) | **FAIL** |

Pairs are perfect tracks / real detections. Pooled cause ranking adds the three tune
incidents from EXP-0009 (3 of 3 top-1 in detections mode). In perfect-track mode it is
0.80 (4 of 5).

## Incidents

| Case | Mode | Opened | True / false / missed | Latency | Window covers cause |
|---|---|---|---|---|---|
| case_02 | perfect, detections | e-stop at 13.5 s, window 3.5–23.5 s | 1 / 0 / 0 | 0.0 s | yes |
| case_06 | perfect, detections | blocked zone at 44.1 s, window 14.1–44.9 s | 1 / 0 / 0 | 0.1 s | yes |

## Behaviours the golden cases exist for

| Case | Criterion | Perfect tracks | Real detections |
|---|---|---|---|
| C02 | 1. E-stop incident, window covers the entry | PASS | PASS |
| C02 | 2. P01's unseen interval named, gap recall ≥ 0.90 | PASS (1.00) | PASS (1.00) |
| C02 | 3. P01 hypothesis worded *Possible* | **FAIL**: no P01 hypothesis; a forklift ranked *Possible* | **FAIL**: same |
| C02 | 4. *Cannot determine* claim citing that gap | **FAIL**: gap in `report.gaps` and limitations only | **FAIL**: same |
| C02 | 5. Neither silent nor confidently wrong about P01 | PASS | PASS on P01; one false *Observed* forklift claim |
| C06 | 1. Blocked-zone incident | PASS | PASS |
| C06 | 2. Both F01 and F02 ranked with scores | **FAIL**: F02 only | **FAIL**: no cause |
| C06 | 3. F02 in the top two | PASS (top-1, *Likely contributed*) | **FAIL** |

## Baseline against learned component

| Component | Baseline | Learned | case_02 | case_06 |
|---|---|---|---|---|
| Detector | COCO `yolo11n.pt` | `yolo11n-rewind-v1` | 0 detections of any class, against robot 0.99 and forklift 0.98 recall | 0 detections, against pallet 0.97 and forklift 0.26 recall |
| Cross-camera appearance | geometry and time only (`no-appear`) | colour-histogram descriptors | false links 0 → 2, recall 0.09 → 0.18 | false links 0 → 0, recall 0.50 → 0.67 |

## Unscored measurements

| Class | case_02 precision / recall | case_06 precision / recall | Proposal |
|---|---|---|---|
| Forklift | 0.687 / 0.980 | 0.905 / 0.259 | No floor: F02 is never detected (EXP-0010); a floor set on this would describe the colour gap, not the detector |
| Pallet | — | 0.986 / 0.971 | ≥ 0.95, consistent with case_04 (1.000 / 0.999) |

## Post-golden, beside the held-out numbers (EXP-0011)

Measured 2026-09-14 after the fixes F3–F7 and the F1 retrain, with `case_02` and
`case_06` open; the held-out columns above are not replaced. Detector `yolo11n-rewind-v1`
(v2 measured, not promoted). Log `artifacts/post-golden-F4-2026-09-14.log`.

| Metric | Floor | Held-out | Post-golden (v1) | Post-golden, v3 (EXP-0013) |
|---|---|---|---|---|
| Detection recall / precision, person | ≥ 0.95 / ≥ 0.95 | 0.065 / 0.875 **FAIL** | 0.065 / 0.875 **FAIL** | 0.062 / 0.870 **FAIL** (F2) |
| Detection recall / precision, robot | ≥ 0.95 | 0.991 / 0.998 PASS | 0.991 / 0.998 PASS | 0.992 / 0.998 PASS |
| Detection recall / precision, forklift (unscored) | — | 0.980 / 0.687 (C02); 0.259 / 0.905 (C06) | 0.980 / 0.986; 0.259 / 0.908 | 0.996 / 0.999; **0.930 / 0.956** |
| ID switches, worst camera | ≤ 2 | 2 PASS | 1 PASS | **4 FAIL** (C06 CAM_A, F9; C02: 1) |
| Zone-event precision / recall, real pipeline | ≥ 0.85 / ≥ 0.90 | 0.38 / 0.53 **FAIL** | 0.58 / 0.37 **FAIL** | 0.57 / 0.47 **FAIL** |
| Event timing error, max | ≤ 0.5 s | 0.40 s PASS | 0.40 s PASS | 0.40 s PASS |
| Cross-camera false-link rate | ≤ 0.05 | 0.25 **FAIL** | 0.29 **FAIL** | **0.00 PASS** |
| Cross-camera recall | ≥ 0.65 | 0.35 **FAIL** | 0.29 **FAIL** | 0.16 **FAIL** |
| Evidence coverage / unsupported-claim rate | ≥ 0.95 / 0.00 | 1.00 / 0.00 PASS | 1.00 / 0.00 PASS | 1.00 / 0.00 PASS |
| Gap recall | ≥ 0.90 | ≥ 0.995 PASS | ≥ 0.995 PASS | 1.00 PASS |
| Cause top-3 / top-1, detections | 1.00 / ≥ 0.67 | 3 of 5 / 0.60 **FAIL** | 3 of 5 / 0.60 **FAIL** | 4 of 5 / 0.60 **FAIL** |
| Cause top-3 / top-1, perfect tracks | — | 1.00 / 0.80 | 1.00 / 0.80, both golden causes now ranked | 1.00 / 0.80 |

The v3 column is `yolo11n-rewind-v3`, trained after the golden run on the tune cases
plus `case_07` (dataset `v1.1`), promoted 2026-09-15 (EXP-0013). Pooled zone events
for v3: C02 0.50 / 0.80, C06 0.67 / 0.29. The one regression, C06 CAM_A's switches,
is a pallet track flipping while a forklift pushes it (F9); v1 never saw the pusher.

| Behaviour | Held-out (perfect / detections) | Post-golden | v3 |
|---|---|---|---|
| C02.3 P01 worded *Possible* | FAIL / FAIL | PASS / FAIL | PASS / FAIL (F2) |
| C02.4 *Cannot determine* claim cites the gap | FAIL / FAIL | PASS / PASS | PASS / PASS |
| C02.5 Not confidently wrong | PASS / one false *Observed* claim | PASS / PASS | PASS / PASS |
| C06.2 Both forklifts ranked | FAIL / FAIL | PASS / FAIL | PASS / **PASS** (v3) |
| C06.3 F02 in the top two | PASS / FAIL | PASS / FAIL | PASS / **PASS** (v3) |

## Raw reports

`detection-finetuned-case_02-2026-09-14T134818Z` · `detection-finetuned-case_06-2026-09-14T134828Z` ·
`detection-baseline-case_02-2026-09-14T134837Z` · `detection-baseline-case_06-2026-09-14T134846Z` ·
`tracking-on-detections-2026-09-14T134904Z` · `events-on-truth-2026-09-14T134905Z` ·
`events-on-detections-2026-09-14T134923Z` · `identity-2026-09-14T134942Z` ·
`incidents-2026-09-14T135000Z` · `reasoning-2026-09-14T135019Z`

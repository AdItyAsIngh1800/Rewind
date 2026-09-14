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

## Raw reports

`detection-finetuned-case_02-2026-09-14T134818Z` · `detection-finetuned-case_06-2026-09-14T134828Z` ·
`detection-baseline-case_02-2026-09-14T134837Z` · `detection-baseline-case_06-2026-09-14T134846Z` ·
`tracking-on-detections-2026-09-14T134904Z` · `events-on-truth-2026-09-14T134905Z` ·
`events-on-detections-2026-09-14T134923Z` · `identity-2026-09-14T134942Z` ·
`incidents-2026-09-14T135000Z` · `reasoning-2026-09-14T135019Z`

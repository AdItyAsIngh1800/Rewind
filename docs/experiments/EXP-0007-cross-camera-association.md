# EXP-0007: Cross-camera association, and what appearance adds

- **Date:** 2026-09-13
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Temporal + geometric + colour-histogram scoring links same-entity segments across cameras at a false-link rate ≤ 0.05 (charter §6), and the histogram adds recall over time and geometry alone (spec §D4 baseline comparison) |
| Dataset version | `v1`, per-actor colour render; tune cases `case_01/03/04/05`; golden pair sealed |
| Preprocessing | `process_camera` with `yolo11n-rewind-v1:native:conf0.25:iou0.5:edge16` and `bytetrack:buf30:match0.9:fps10`; segment positions by camera back-projection at half class height; 12×4 hue-saturation histograms from the centre half of each box |
| Model / tracker version | `assoc:thr0.75:amb0.1:w0.35/0.4/0.25:gap15.0` |
| Hyperparameters | None swept. Three modes per case: **perfect** (ground-truth boxes, no descriptors), **detections** (full pipeline), **no-appearance** (the same detections with descriptors withheld, so appearance scores a neutral 0.5) |
| Hardware | Apple M4, MPS |
| Config version | `v0.1.0` |

## Metrics

`identity-2026-09-13T112213Z`. Recall is over *comparable* true pairs: same entity,
different cameras, both segments localised and within the hand-over window. An
UNKNOWN is a refusal, never counted as an error.

| Mode | Linked | False links | False-link rate | True pairs recalled | Recall | UNKNOWN |
|---|---|---|---|---|---|---|
| Perfect tracks | 23 | 0 | **0.00** | 23 / 25 | 0.92 | 2 |
| **Detections** | 20 | 0 | **0.00** | 20 / 27 | **0.74** | 5 |
| No appearance | 19 | 0 | **0.00** | 19 / 27 | 0.70 | 6 |

Per case, true pairs recalled:

| Case | Perfect | Detections | No appearance |
|---|---|---|---|
| case_01 | 4 / 6 | 5 / 8 | 6 / 8 |
| case_03 | 7 / 7 | 5 / 7 | 5 / 7 |
| case_04 | 6 / 6 | 4 / 6 | 3 / 6 |
| case_05 | 6 / 6 | 6 / 6 | 5 / 6 |

Detections have more true pairs than perfect tracks because P01's long-gap
re-acquisition in `case_01 CAM_A` splits it into two segments (EXP-0004).

Before the EXP-0004 edge rule, `case_03` fragmented into 11 segments and its
detections recall was 0.50; with it, 8 segments and 0.71.

## Failure cases

Every UNKNOWN in the detections mode, plus the perfect-track ones, traced to its signals.

| Case, pair | Decision | Cause |
|---|---|---|
| `case_01` P01 CAM_A ↔ CAM_B/CAM_C, perfect | UNKNOWN at 0.71–0.72 | P01 is unseen for ~7 s crossing the walkway, so the hand-over scores temporal 0.54–0.56. Perfect tracks carry no descriptors and nothing lifts the pair past 0.75. The real pipeline's histogram does: CAM_A ↔ CAM_B links at 0.91 (appearance 0.70) |
| `case_01` P01 CAM_A ↔ CAM_C, detections | UNKNOWN at 0.79, above threshold | CAM_A holds two P01 fragments. Appearance 0.32 pulled this pair within the 0.10 ambiguity margin of the other fragment, so the rule refused. Without appearance the margin was wider and it linked |
| `case_03` P01 CAM_A ↔ CAM_B | UNKNOWN at 0.738 with appearance, LINKED at 0.762 without | One person, two viewing angles, appearance 0.40: 0.012 under the threshold |
| `case_03` P02 CAM_A ↔ CAM_B | UNKNOWN in every mode (0.42 / 0.54) | P02 is cut by CAM_B's bottom edge. Its box centre is not its centre (geometric 0.17) and the crop is a washed-out top face (appearance 0.02). A correct refusal on unusable evidence |
| `case_04` PL3 CAM_C ↔ CAM_A and CAM_B | UNKNOWN at 0.73, geometric 0.92–0.95 | From the steep CAM_C the pallet's histogram shares almost nothing with the side views (appearance 0.02–0.03). Appearance vetoed two geometrically certain links |

**The distractor.** `case_03` exists to tempt a false link between P01 and P02.
Every cross pair between them scored 0.40–0.43 with appearance and 0.48–0.56
without. Geometry had already put them at 0.00–0.20, so the decoy never approached
the threshold in either mode. The histogram does separate them (P01 ↔ P01 0.40–0.83,
P01 ↔ P02 0.00–0.28), but on these cases it was never the deciding signal.

## Result

**Zero false links in 62 LINKED decisions across all three modes.** The charter
floor is met, but with no near-miss to measure the margin: none of the tune cases
puts two same-class entities close in both space and time across cameras.

The colour histogram is worth one pair net (20 vs 19), and that net hides a swing in
both directions:

- **It rescues** pairs where geometry is uncertain and the entity looks the same from
  both cameras: R12 `case_03` CAM_A ↔ CAM_B 0.70 → 0.82; F01 `case_04` CAM_A ↔ CAM_B
  0.66 → 0.77 (geometric 0.47, appearance 0.91); P01 `case_01` across the 7 s gap.
- **It vetoes** pairs where the viewpoint changes the colour distribution: the pallet
  from overhead, a person from two angles.

A hue-saturation histogram is viewpoint-dependent for anything whose faces differ in
colour or shading. That is the baseline's measured ceiling, and it limits recall,
never the false-link rate.

## Decision

**Adopt association as configured** (threshold 0.75, margin 0.10, weights
0.35/0.40/0.25) for Gate 3. Do not retune weights on these cases: each change that
recovers the vetoed pallet also loses the rescued forklift, and the evidence is five
decisions deep. Tuning at that depth is fitting the tune set.

## Next experiment

Spec §D4's advanced method: a crop embedding (OSNet or CLIP) against this histogram,
in the same three modes, scored false-link rate first. Optional under the roadmap.
Worth running if E7's hypotheses need a link the histogram refuses; not before.

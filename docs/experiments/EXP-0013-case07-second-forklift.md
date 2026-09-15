# EXP-0013: A tune case with the second forklift colour, seen truncated

- **Date:** 2026-09-15
- **Status:** Running. Decision rule written before the harness ran (below).

| Field | Value |
|---|---|
| Hypothesis | EXP-0011 traced F1 to data, not training: no tune case shows a forklift in F02's colour, and none shows a forklift cut by a frame edge. A tune case that shows both lets a detector at the *default* hue jitter find F02 in `case_06` **without** losing the truncated F01 in `case_02` that the colour-blind `v2` lost. |
| What this is not | A held-out result. `case_02` and `case_06` were opened in EXP-0010. Their numbers here say whether the traced failure is addressed; they never replace EXP-0010. The new case was designed from the *failure catalogue's* description of the golden cases, not by looking at golden frames again. |
| Dataset version | `v1` plus `case_07`; manifest `v1.1` once rendered. `case_07` is `case_04`'s script with the forklift as `F02` (navy, the existing `actor_colours` override) and one extra leg: after leaving the pallet in Z2 at 14 s it drives to (18.3, 9.5), where `case_02`'s F01 parks, cut by CAM_B's bottom edge, and stays. `ml/configs/cases_v1.json`. |
| Preprocessing | `scripts/ml/export_yolo_dataset.py`, `TRAIN_CASES` + `case_07`, validation `case_05` unchanged, stride 5. Golden ids asserted absent from every split, as before. |
| Model | `yolo11n-rewind-v3`: `yolo11n.pt`, 20 epochs, seed 0, **default hue jitter** (0.015). The same recipe as `v1`; only the data differs. |
| Hardware | Apple M4, MPS. |
| Harness | Every script EXP-0011 ran for F1, on all seven cases, `REWIND_DETECTOR_CHECKPOINT` at v3: `artifacts/post-golden-F1b-2026-09-15.log`. |

## Decision rule, set before the run

`v3` is promoted to the worker default if and only if, against `v1`:

1. `case_06` forklift recall rises from 0.259 to at least what `v2` reached (0.938),
   and F02 is ranked as a cause with real detections; and
2. `case_02` keeps every guarantee `v1` holds: forklift recall ≥ 0.98 (v2: 0.466),
   ID switches on the worst camera ≤ 2 (v2: 3), person precision not below `v1`'s
   0.875; and
3. tune detection, tracking, events, identity, incidents and causes do not regress
   past the third decimal on `case_01`, `03`, `04`, `05`.

Any failure of (2) or (3) means `v3` is recorded, not promoted, as `v2` was: a
guarantee that holds is never traded for progress on one that does not.

## Metrics

Filled in from the log.

## Failure cases

## Result

## Decision

## Next experiment

# EXP-0013: A tune case with the second forklift colour, seen truncated

- **Date:** 2026-09-15
- **Status:** Complete 2026-09-15. Decision rule written before the harness ran; results and the promotion decision below.

| Field | Value |
|---|---|
| Hypothesis | EXP-0011 traced F1 to data, not training: no tune case shows a forklift in F02's colour, and none shows a forklift cut by a frame edge. A tune case that shows both lets a detector at the *default* hue jitter find F02 in `case_06` **without** losing the truncated F01 in `case_02` that the colour-blind `v2` lost. |
| What this is not | A held-out result. `case_02` and `case_06` were opened in EXP-0010. Their numbers here say whether the traced failure is addressed; they never replace EXP-0010. The new case was designed from the *failure catalogue's* description of the golden cases, not by looking at golden frames again. |
| Dataset version | `v1.1`: `v1` plus `case_07` (`data/manifests/v1.1.json`, release `data-v1.1`; every `v1` file unchanged, 48 checksums). `case_07` is `case_04`'s script with the forklift as `F02` (navy, the existing `actor_colours` override) and one extra leg: after leaving the pallet in Z2 at 14 s it drives to (18.3, 9.5), where `case_02`'s F01 parks, cut by CAM_B's bottom edge, and stays. `ml/configs/cases_v1.json`. |
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

Tune cases (`case_01`, `03`, `04`, `05`): events, identity, incidents and causes
**identical to v1 in every row**; detection within 0.003 of v1 on every class.
Validation mAP50 / mAP50-95 on `case_05`: 0.995 / 0.983 (v1 0.986, v2 0.982).

| Measure | v1 (post-F4) | v2 | v3 |
|---|---|---|---|
| case_06 forklift precision / recall | 0.908 / 0.259 | 0.981 / 0.938 | 0.956 / 0.930 |
| case_06 pallet precision / recall | 0.992 / 0.971 | — | 0.984 / 0.981 |
| case_06 ranked causes, detections | F01, PL3 | F01, F02, F01, fragment | F01, F02, F01, PL3 (F02 in the top two) |
| case_06 zone events P / R, detections | 0.60 / 0.21 | 0.75 / 0.43 | 0.67 / 0.29 |
| case_06 cross-camera recall / false links | 0.38 / 0 | 0.08 / 0 | 0.20 / 0 |
| case_06 ID switches, worst camera | 0–1 | 1 | **4** (CAM_A, PL3) |
| case_02 forklift precision / recall | 0.986 / 0.980 | 1.000 / 0.466 | 0.999 / 0.996 |
| case_02 person precision / recall | 0.875 / 0.065 | 0.257 / 0.056 | 0.870 / 0.062 |
| case_02 ID switches, worst camera | 1 | 3 | 1 |
| case_02 zone events P / R, detections | 0.57 / 0.80 | 1.00 / 0.80 | 0.50 / 0.80 |
| case_02 false links / cross-camera recall | 2 of 4 (0.50) / 0.22 | 2 of 6 (0.33) / 0.40 | **0 of 1 (0.00)** / 0.11 |
| Golden false-link rate, pooled (floor ≤ 0.05) | 0.25 | — | **0.00** |
| Cause top-3 / top-1, five incidents, detections | 3 of 5 / 0.60 | 4 of 5 / 0.60 | 4 of 5 / 0.60 |
| Evidence coverage / unsupported claims, every report | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| `case_07` itself (a training case) | — | — | forklift 0.997 / 1.000; 0 switches; incident opened, F02 top-1 |

Log: `artifacts/post-golden-F1b-2026-09-15.log`. The incidents and reasoning harnesses
carry a per-case truth table and did not know `case_07`; both were rerun after adding
it (same log, "rerun" section). No golden number changed between the two runs.

## Failure cases

- **F8, new to the catalogue and present under v2 as well.** On `case_06` CAM_A, F01
  leaves the view at 12.2 s and F02 enters nearby at 12.6 s; ByteTrack's 3 s buffer
  continues F01's track id onto F02, so two forklifts share `CAM_A-T001`. The
  ID-switch metric counts an entity changing track, never a track changing entity, so
  the harness reports no switch for it. `docs/failures/F8-case_06-CAM_A-f128.jpg`.
- **F9, the one regression.** PL3 on the same camera alternates between two pallet
  tracks four times between 20.9 and 22.2 s, while F02 pushes it: the pallet's visible
  sliver under the forklift's front is detected twice (`F9-case_06-CAM_A-f212.jpg`).
  Four switches against the floor of two. v1 held that floor there because it never
  detected the forklift doing the pushing.
- Person recall on `case_02` unchanged at 0.062 (F2): with F02 found and the frame-cut
  forklift kept, the postmortem's test that F2 is a visibility limit and not a
  training gap is passed.

## Result

The hypothesis held. Data, not augmentation, was the fix: at default hue jitter, one
tune case with the second colour and a truncated view lets the detector find F02
(0.930 recall against 0.259) **and** keep `case_02`'s frame-cut forklift (0.996
against v2's 0.466), with every tune number unchanged. Two side effects: `case_02`'s
false links disappear (the cleaner forklift boxes leave no fragment track to link), so
the pooled golden false-link rate meets its floor for the first time; and seeing F02
exposes two tracker behaviours the metric either counts (F9) or cannot see (F8).

Against the pre-registered rule: criterion 1 in substance (F02 found and ranked; 0.930
against the 0.938 bar, eight boxes), criterion 2 met (forklift 0.996, switches 1;
person precision 0.870 against 0.875, one box), criterion 3 met exactly. The rule did
not name `case_06`'s switch floor, which v1 held only by not seeing the pusher.

## Decision

**Promote `yolo11n-rewind-v3`** to the worker default. Owner decision, on the numbers
above and the trace of F9: the regression is a tracker behaviour during contact, not
a detector one, and the alternative keeps a detector that cannot see one of the two
forklift colours in the scene. `v1` remains the checkpoint of record for EXP-0010's
held-out numbers; `v2` stays measured and unpromoted.

New baseline: `yolo11n-rewind-v3`, dataset `v1.1`. `final.md` gains a v3 column beside
the held-out and post-golden ones; the held-out column is untouched.

## Next experiment

Tracker settings on `case_07` (a tune case that now contains the push and the
frame-edge view): ByteTrack buffer and match threshold, and a class-and-appearance
gate on re-matching a lost track (F8), measured on the golden pair beside these
numbers. And a harness measure for a track that carries two entities, so F8 has a
number.

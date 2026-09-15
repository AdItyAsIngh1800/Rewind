# Postmortem: the held-out cases failed every perception floor they could fail

- **Incident ID:** PM-0001
- **Date:** 2026-09-14 (golden run 19:18–19:20 +0530)
- **Owner:** Aditya Singh

The single biggest thing that went wrong, as the roadmap's final audit asks. Not the
frozen-actor render (repaid in a day) and not the misreported container speed
(corrected the same day): this one shaped the final numbers and could not be repaid
inside the schedule.

## Impact

On the two held-out cases, opened once under a pre-registered protocol (EXP-0010):
person detection recall 0.065 against a floor of 0.95; the second forklift in
`case_06` detected in 0 of 697 ground-truth boxes; from those, zone-event recall 0.53,
cross-camera recall 0.35 and false-link rate 0.25, cause ranking 3 of 5. Eight of
fifteen charter floors failed. The reasoning layer's behaviours passed with perfect
tracks and partly with real detections, so the project's argument stands, but the
benchmark report's first table is mostly **FAIL**, and that is what a reader sees first.

## Detection

At the golden run itself, E9.1, seventeen roadmap weeks after the split was made. That
is by design — the cases were sealed — and it is also the point: nothing before E9.1
could have noticed, because nothing before E9.1 was allowed to look.

## Timeline

| Time | Event |
|---|---|
| 2026-09-09 (PS-6) | Scene spec authors six cases. `case_06` gets a second forklift, in navy, so the blocked-zone case has two candidate causes. `case_02` puts the person behind a forklift for the occlusion the UNKNOWN feature needs. |
| 2026-09-09 (E1.3) | Split chosen by incident coverage: 4 tune (`01`, `03`, `04`, `05`), 2 golden (`02` occluded e-stop, `06` ambiguous blocked zone). Sealed. |
| 2026-09-11 (E1.2) | Ground truth exported with boxes from 15 % visibility, so that occlusion intervals are precise. |
| 2026-09-13 (E3.1) | `yolo11n-rewind-v1` fine-tuned on the tune cases, Ultralytics' default hue jitter (0.015). mAP50 0.987. Gate 1 signed on tune numbers. |
| 2026-09-14 19:18 | Golden run. F1: F02 never detected. F2: P01 detected in 4 of 297 boxes. F4: a duplicate box on a half-visible forklift seeds a track that gets linked. |
| 2026-09-14 20:00–23:00 | EXP-0011: F3–F7 fixed on pipeline properties and tune data; F1 retrained with full-hue jitter (`v2`), finds F02, loses `case_02`'s frame-cut forklift; not promoted. F2 accepted. |
| 2026-09-15 | Gate 7 recorded as PASS on its criterion, FAIL on the floors. This postmortem. |

## Root cause

**The tune/golden split was chosen for incident coverage and never checked for
appearance coverage.** The golden cases contained two things the tune cases did not:
a forklift colour, and a visibility regime (a person at a fifth of their silhouette).
A detector fine-tuned on three cases learned *forklift* as one colour, and learned
*person* as a mostly visible person, because that is all it was shown. The sealed
discipline that made the benchmark honest also made the gap invisible until the one
moment it could no longer be fixed without contaminating the result.

## Contributing factors

- The scene spec chose distinct forklift colours for the reader's benefit, not the
  detector's, and nobody asked what the tune set taught about colour.
- The 15 % visibility threshold was set for occlusion precision (where does the gap
  start?) and then reused as a detection target (should the detector find this?),
  which it was never meant to be.
- One fine-tuning run at default augmentation; the colour-blind variant was tried
  only after the failure, under a one-run time box, and traded one forklift for
  another.
- Three tune cases is a small world. Every appearance that matters must be in it on
  purpose, because nothing will be in it by accident.

## What worked

- Pre-registration: the run was committed before it happened (`03a0732`), so the
  failures are unarguable.
- The failure catalogue: every miss traced to a frame with the truth box and the
  detector's box side by side (`docs/failures/`).
- The rule that fixes go beside the held-out number, never in its place, held under
  the temptation not to.
- The layered evaluation (perfect tracks / real detections) showed exactly which
  layer failed, so the reasoning work was not blamed for a perception gap.

## What failed

- No dataset audit between E1.3 and sealing. A table of attributes per case — entity
  colours, visibility distribution, camera coverage — would have shown the navy
  forklift in one column and nowhere else.
- Gate 1 signed off detection on tune numbers alone, which is what Gate 1 is, but
  with no statement of what the tune set could not have taught.

## Corrective actions

| Action | Owner | Due |
|---|---|---|
| Re-render one tune case with a second forklift colour (E1 re-render, owed since EXP-0011), retrain, measure beside EXP-0010 | Owner | Before any claim that F1 is fixed |
| Tracked-perfect harness mode (perfect boxes through the real tracker) to separate tracking loss from detection loss | Owner | Next evaluation pass |
| State the ground-truth visibility floor and its consequence in the model card | Done | `ml/models/yolo11n-rewind-v1/limitations.md` |

## Preventive actions

- E1.3 gains a step before sealing: an appearance-coverage table, checked against the
  golden cases' scene specs without rendering or viewing them. Roadmap amendment.
- A Gate 1 line: "what the tune set cannot have taught", written from that table.

## Verification date

When the E1 re-render's retrain is measured on the golden pair beside EXP-0010. If
person recall stays near 0.065 with F02 found, F2 is confirmed as a visibility limit
and not a training gap; if it moves, this postmortem was too kind to the threshold.

# EXP-0010: Golden benchmark — case_02 and case_06, opened once

- **Date:** 2026-09-14
- **Status:** Pre-registered. Everything above "Results" was written and committed before
  any golden-case output was produced or ground-truth file read.

| Field | Value |
|---|---|
| Hypothesis | The pipeline as configured for Gates 1–5 meets the charter §6 floors on two cases it has never seen, names C02's unseen incursion as a gap with the cause only *possible*, and surfaces both of C06's defensible causes with scores |
| Dataset version | `v1`; golden split `case_02`, `case_06` (manifest `split_policy`). Checksums verified against `data/manifests/v1.json` before this record: 16 of 16 files match |
| What was known beforehand | The scene spec (§6.2, §6.6) and the case scripts in `ml/configs/cases_v1.json`, which the pipeline itself reads for robot telemetry. Never read before this run: the rendered clips, `*_gt.json`, and any system output on these cases |
| Model / tracker / config | Exactly as signed off: `yolo11n-rewind-v1:native:conf0.25:iou0.5:edge16`, `bytetrack:buf30:match0.9:fps10`, `assoc:thr0.75:amb0.1:w0.35/0.4/0.25:gap15.0`, `incidents:estop10/10:dwell20+10/10:zonesZ2`, `evidence-0.1.0`, `hypotheses:tau5:look10:w0.35/0.3/0.2/0.15:strong0.7`, `deterministic-0.1.0`; in-group refusals cap hypotheses (option A) |
| Hardware | Apple M4, MPS, same as every tune-case record |

## Pre-registered pass criteria

### Charter §6 floors, signed off at Gates 1–5

| Metric | Floor | Scored by |
|---|---|---|
| Detection recall / precision, person and robot | ≥ 0.95 / ≥ 0.95 | `baseline_detection.py`, fine-tuned checkpoint, per case |
| ID switches per case, per camera | ≤ 2 | `tracking_on_detections.py` |
| Zone-event precision / recall, real pipeline | ≥ 0.85 / ≥ 0.90 | `events_on_detections.py`, pooled over both cases |
| Event timing error | ≤ 0.5 s | same |
| Cross-camera false-link rate | ≤ 0.05 | `identity_on_detections.py`, real pipeline |
| Cross-camera recall | ≥ 0.65 | same |
| Evidence coverage | ≥ 0.95 in every report | `reasoning_on_detections.py`, both modes |
| Unsupported-claim rate | 0.00 in every report | same |
| Gap recall | ≥ 0.90 wherever truth has a gap | same |
| Cause top-3 | 1.00 | same |
| Cause top-1 | ≥ 0.67, pooled over the five incidents (three tune, two golden) in detections mode | same, plus EXP-0009 |

Forklift and pallet detection have no floor yet (Gate 1 deferred it to here). This run
measures them and proposes one; it does not pass or fail on them.

### Behaviours the golden cases exist for (scene spec, written before rendering)

**C02 `ESTOP_OCCLUDED`**, both modes:

1. An e-stop incident opens, with no false positive, and its window covers P01's entry
   into Z1 (about 13.0 s, per the case script).
2. A gap is named for P01 over the unseen interval, gap recall ≥ 0.90.
3. The hypothesis about P01 is worded **Possible**. *Likely contributed* or *Observed*
   is a FAIL: that is the confident incursion the spec forbids. *Conflicting evidence*
   is recorded as an under-claim, not a pass.
4. The report carries a *Cannot determine* claim citing that gap.
5. FAIL outright if no incident opens or no gap is named.

**C06 `BLOCKED_AMBIGUOUS`**, both modes:

1. A blocked-zone incident opens, with no false positive.
2. Both F01 and F02 appear as ranked causes with scores. Only one is a FAIL.
3. F02, the annotated cause, is in the top two. F01 first and F02 second is a pass.

### Expected values written into the harnesses before running

| Case | Incident class | Trigger (s) | Cause time (s) | Cause entity | Source |
|---|---|---|---|---|---|
| case_02 | robot e-stop | 13.5 | 13.0 | P01 | scripted `estop` waypoint; `cause_gt` line in the case script |
| case_06 | blocked zone | 44.0 | 24.0 | F02 | pallet's final stop at 24.0 s plus the 20 s dwell; `cause_gt` line |

## Predictions, written before running

- **C06 criterion 2 is at risk.** The pallet stops at 10 s, is pushed at 22–24 s, and
  rests again from 24 s, so the dwell trigger should come from the second stop, at
  about 44 s. The class 2 window starts 10 s before the stop (EXP-0008), at about 14 s.
  F01's drop at 10 s is then outside the window, and the ranker only considers events
  inside it. The prediction is that F01 is **not** surfaced and criterion 2 fails. This
  is a design consequence found by reading the ranker, not by looking at the case; it is
  not being fixed first, because the held-out run exists to measure the system as it
  was signed off.
- **C02 criterion 3 depends on candidate generation.** The Z1 entry is unobserved by
  construction, so there may be no event to build a P01 candidate from, in which case
  the ranker falls back to a single UNKNOWN hypothesis. That would name the gap
  (criterion 2) but rank no possible cause.

## Procedure

Run once, in this order, with outputs left as written:

    uv run python scripts/evaluation/baseline_detection.py --case case_02 --checkpoint ml/models/yolo11n-rewind-v1/best.pt --native-classes
    uv run python scripts/evaluation/baseline_detection.py --case case_06 --checkpoint ml/models/yolo11n-rewind-v1/best.pt --native-classes
    uv run python scripts/evaluation/baseline_detection.py --case case_02    # COCO baseline
    uv run python scripts/evaluation/baseline_detection.py --case case_06    # COCO baseline
    uv run python scripts/evaluation/tracking_on_detections.py case_02 case_06
    uv run python scripts/evaluation/events_on_truth.py case_02 case_06
    uv run python scripts/evaluation/events_on_detections.py case_02 case_06
    uv run python scripts/evaluation/identity_on_detections.py case_02 case_06
    uv run python scripts/evaluation/incidents_on_detections.py case_02 case_06
    uv run python scripts/evaluation/reasoning_on_detections.py case_02 case_06

**The first run is the held-out result.** Its reports are committed unchanged. Any later
change to code or configuration that moves a golden number is logged in the deviation
ledger as post-golden, and its numbers are reported beside these, never in their place.

## Results

_Not yet run._

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

- **Run:** 2026-09-14, 19:18–19:20 +0530, once, in the order above; all ten commands exited 0.
- **Log:** `artifacts/golden-run-2026-09-14.log`.
- **Tables:** `artifacts/benchmark-reports/final.md` holds every number against its floor.
- **Unchanged since pre-registration:** code, configuration and the pre-registration above.

### Verdict

| | Held |
|---|---|
| Incidents | 4 of 4 opened, 0 false, latency ≤ 0.1 s, every window covers its cause |
| Grounding | Evidence coverage 1.00 and unsupported-claim rate 0.00 in all four reports |
| Uncertainty | Every truly unseen interval named: gap recall ≥ 0.995 |
| Perception that transferred | Robot detection 0.99 / 1.00; ID switches ≤ 2; event timing ≤ 0.40 s |
| No confident incursion | P01 is never said to have entered Z1; C06 on detections says no cause can be determined rather than naming the wrong one |

| | Failed |
|---|---|
| Charter floors | Person detection (0.065 recall), zone events (0.38 / 0.53), cross-camera false links (0.25) and recall (0.35), cause top-3 (3 of 5) and top-1 (0.60) |
| C02 behaviour | No *Possible* hypothesis about P01, and no *Cannot determine* claim about the interval nobody saw |
| C06 behaviour | F01 never ranked; on real detections, no cause at all |
| Truth of a claim | One false *Observed* claim on C02 detections, fully cited |

### Pre-registered predictions

- **C06, F01 outside the window: confirmed exactly.** The trigger came from the second
  stop (44.1 s), the window opened at 14.1 s, and F01's drop at 10 s was invisible to the
  ranker even with perfect tracks.
- **C02, UNKNOWN fallback: wrong in detail.** The ranker did not fall back to UNKNOWN. The
  parked forklift F01, which did cross into Z1 at 3.7 s, became a *Possible* candidate
  instead (score 0.55).

### Failure analysis

Diagnostics re-ran the unchanged harness and perception code with capture hooks; every
number matched the first run, so the pipeline is deterministic and the traces describe
the run above.

**F1. F02 is never detected: 0 of 697 true boxes, at visibility up to 0.93.** F02 is the
only navy actor (per-actor colours, ledger 2026-09-13), and no tune case has a navy
forklift. The fine-tuned detector learned *forklift* as F01's colour. This alone drives
C06's forklift recall to 0.26, its event recall to 0.43, the absence of any F02 track
for identity, and the detections-mode report finding no cause.

**F2. A mostly hidden person is not found.** On CAM_A, C02's person has a median
visibility of 0.20 behind the parked forklift; the detector finds 4 of 297 boxes. Ground
truth emits anything at least 15% visible (scene spec §7), so the floor counts these, and
it fails.

**F3. A stationary object on a zone edge flickers in and out, and becomes a false
*Observed* claim.** F01 parks at y = 9.5, exactly Z1's boundary. Its back-projected
position crosses the edge repeatedly on real detections: entered at 11.2 s, left 11.3 s,
entered 14.6 s, left 15.9 s, entered 16.2 s, left 17.1 s, all from `CAM_A-T002`, which is
truly F01. The report states *"Observed: Forklift entered Z1 at 11.2 s"*, and the top
hypothesis rests on it: *"Possible: Forklift … entered Z1 at 11.2 s, 2.3 s before the
robot's emergency stop"*. The unsupported-claim rate stays 0.00 because the citation
resolves to a real event. **Gate 5 guarantees that every claim is traceable, not that
the evidence it traces to is true.** The same boundary sensitivity explains most of
C02's 11 false events, and C06's projected-position precision of 0.47, where the pallet
rests 0.2 m inside Z2's edge.

**F4. A duplicate box on a partly visible forklift is joined to it across cameras.**
`golden-case_02-CAM_B-f112-duplicate-box.jpg`: the forklift is cut off by CAM_B's bottom
edge, and the detector emits the whole machine (0.87) and a second box on its dark front
face (0.60). Their overlap (IoU about 0.27) is under the 0.5 NMS threshold, so both
survive. The second box starts track `CAM_B-T008`, which matches no true box (410
unmatched forklift boxes in CAM_B). Identity linked it to F01 on CAM_A (0.81) and CAM_C
(0.97): the two false links behind the 0.50 rate. Both join a duplicate of the same
physical forklift, so no trajectory between two real entities was made up, but the
metric as registered counts them and the FAIL stands. Without appearance (`no-appear`)
both are refused: the forklift's own colour is what accepted them.

**F5. No hypothesis can be built for an entity whose decisive move was unseen.**
Candidates come from observed events inside the window. P01's Z1 entry at about 13 s lies
in the unseen interval (11.0–14.8 s), by design, so there is no event to build from. The
spec's required outcome, *possible because consistent with the surrounding evidence*,
needs a candidate generated from a gap (last seen approaching, next seen past the lane),
which the ranker does not do.

**F6. The unseen interval is not written as a claim.** The generator writes *Cannot
determine* only for gaps on entities a hypothesis names or holds against it. P01 is in no
hypothesis, so its gap reaches the graph, `report.gaps` and the limitations count, but a
reader of the claims is never told that the critical moment was unseen. That is the
behaviour the project is named for.

**F7. The blocked-zone window starts too late for an earlier contributor.** The window
opens 10 s before the object's final stop (EXP-0008). An object that arrived, stopped,
was moved and stopped again has its first contributor outside the window: F01 at 10 s.

### What these are not

None of F1–F7 is a threshold fitted too tightly to the tune cases. Retuning any number on
them would not detect a navy forklift, generate a candidate from a gap, or widen a
window. They are three perception gaps (F1 colour, F2 heavy occlusion, F4 duplicate edge
boxes), one event-extraction gap (F3 zone-edge hysteresis), and three reasoning design
gaps (F5–F7).

## Decision

**Recorded as the held-out result, unchanged.** Gate 7's own criterion, that results and
failure modes are measurable, is met: every floor is measured and every failure traced.
The system does not meet the charter floors on unseen cases.

Which of F1–F7 to fix is an owner decision. Every fix is post-golden: re-measured on all
six cases with `case_02` and `case_06` labelled *no longer held-out*, reported beside this
record, never in its place.

## Next experiment

The owner-selected post-golden fixes, re-measured on all six cases. E9.2 (failure
catalogue with frames and model cards), E9.3 (profiling) and E9.4 (test suite) proceed
regardless.

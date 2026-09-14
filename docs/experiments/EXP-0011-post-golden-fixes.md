# EXP-0011: Post-golden fixes for EXP-0010's failures

- **Date:** 2026-09-14
- **Status:** Closed 2026-09-14. One section per fix, in the owner's order: F3, F6, F5,
  F7, F4, F1; F2 accepted as a documented limitation. Verdict at the end.

| Field | Value |
|---|---|
| What this is not | A held-out result. `case_02` and `case_06` were opened in EXP-0010 and are **no longer held-out**. Their numbers here show whether a fix addressed its traced failure; they never replace EXP-0010, and no fix is tuned until a golden number comes back |
| Where thresholds come from | The tune cases (`case_01`, `case_03`, `case_04`, `case_05`), or a documented property of the pipeline. A golden case may show that a rule is needed; it does not choose the rule's value |
| Measured after each fix | Every harness the fix can move, on all six cases, both modes |
| Hardware | Apple M4, MPS, as EXP-0010 |

## F3 — a still object on a zone edge

**Failure (EXP-0010).** F01 parks with its centre exactly on Z1's edge in case_02. On
real detections its estimated position crossed the edge repeatedly, and the report
stated *"Observed: Forklift entered Z1 at 11.2 s"* with the top hypothesis resting on it.
It was the one failure that asserted something false at the *Observed* level.

**Change.** `geometry.confirmed_transitions` replaces raw zone transitions in the event
extractor (`events:…:edge0.5`). A run of samples on the other side of an edge counts as
a crossing if it reaches **0.5 m** past the edge, or if the object **moves 0.5 m** across
it (median position before the run against after). Only a shallow excursion by a still
object is dropped. A kept crossing keeps its original timestamp, so no real crossing is
delayed; that delay was EXP-0005's reason for rejecting hysteresis.

**Where 0.5 m comes from.** `scripts/evaluation/localisation_jitter.py` on the tune cases
only: real-detection positions of a still object wobble by at most 0.40 m (pallet), 0.31 m
(person) and 0.09 m (robot). 0.5 m is the first 0.1 m step above that. No tune case has a
stationary forklift, so forklift wobble is unmeasured.

**First version, corrected on a tune case.** The first rule used depth alone. On the tune
cases it dropped case_03's P01 clipping Z2's corner, 0.13 m deep while walking (true in
ground truth), and with it the 3 m-deep exit that followed: tune event recall fell from
0.92 to 0.84, below the floor. The movement condition was added for that tune case, and
the tune numbers recovered.

### Results

Before = EXP-0010 golden run and the Gate 2 tune reports; after = revised rule
(`events-on-truth-2026-09-14T152410Z`, `events-on-detections-2026-09-14T152505Z`,
`incidents-2026-09-14T152600Z`, `reasoning-2026-09-14T152652Z`). The depth-only run's
reports (`…T152012Z`, `…T152105Z`, `…T152159Z`, `…T151842Z`) are kept, with the command
error and both runs, in `artifacts/post-golden-F3-2026-09-14.log`.

| Measure | Before | After |
|---|---|---|
| Tune zone events, real detections, precision / recall | 0.88 / 0.92 | **0.92 / 0.92** |
| Tune zone events, truth positions, recall | 1.00 | 1.00 |
| Tune incidents, cause top-1 (both modes) | 3 of 3 | 3 of 3 |
| case_02 false events, real detections | 11 | **3** |
| case_02 report: false *Observed* claim | "Forklift entered Z1 at 11.2 s" | **gone**; top hypothesis now rests on the forklift's real entry at 3.95 s |
| Golden zone events, real detections, precision / recall | 0.38 / 0.53 | 0.55 / 0.32 |
| case_06 zone events, truth positions, recall | 0.79 | **0.36** |
| case_06, perfect tracks: ranked cause | F02, *Likely contributed* | **none** (UNKNOWN) |
| Evidence coverage / unsupported-claim rate, every report | 1.00 / 0.00 | 1.00 / 0.00 |

**Fixed:** the false *Observed* claim, and 8 of case_02's 11 false events.

**Cost, measured on case_06.** F01 noses 0.2 m into Z2 to drop the pallet and backs out;
F02 touches the edge while pushing it and reverses. Measured either side of a
touch-and-reverse, a vehicle has barely moved, so both crossings read as wobble. The
blocked-zone ranker builds candidates only from zone entries and exits, so with perfect
tracks case_06 lost its only candidate, F02.

**Why F3 stops here.** Adjusting the rule further until case_06's touches return would
shape it around a golden case. The cost is carried to F7, which builds blocked-zone
candidates from proximity to the resting object rather than from zone entries.

**Known limit.** Wobble that starts within half a second of arriving still reads as
movement, because the "before" positions include the approach.

## F6 — an unseen interval before the trigger is written as a claim

**Failure.** The generator wrote *Cannot determine* only for gaps on entities a
hypothesis named or held against it. case_02's person was in no hypothesis, so the
interval nobody saw reached the graph and the limitations count but never a claim.

**Change.** `deterministic-0.2.0`: a gap on any non-robot entity that overlaps the
ranker's look-back before the trigger is claimed. The robot is left out because its
state at the trigger comes from telemetry, which never goes dark.

**Results** (`reasoning-2026-09-14T153002Z`, with F3): case_02 perfect gains two
*Cannot determine* claims about P01 before the stop (was none); tune cases gain one or two
such claims each about entities unseen before their trigger; nothing else moves.

## F5 — a possible cause whose decisive move was unseen

**Failure, traced.** With perfect tracks the extractor *does* emit P01's Z1 entry as a
bounded event: the crossing fell in the 11.0–14.8 s gap, and the event is stamped at the
reappearance, 14.8 s, with `during_gap`. The ranker judged it by its stamp, 0.8 s after
its window closed, and discarded it. There was no candidate to be *possible*.

**Change.** The e-stop ranker judges a bounded event by the interval it happened in.
It counts if that interval reaches into the look-back; temporal precedence is taken
from the middle of the part of the interval that precedes the stop; the description
says *"at some moment between 11 and 14.8 s while no camera saw it"*. The level stays
capped at *Possible* by the existing bounded-event rule.

**Results** (`post-golden-F5-2026-09-14.log`): case_02 perfect ranks **P01 first,
Possible**, F01 second. Tune cases unchanged. case_02 on real detections cannot gain:
P01 is found in 4 of 297 frames after the gap (F2), so there is no reappearance to
bound the entry with.

## F7 — a blocked zone's earlier contributor

**Failure.** The window opened 10 s before the object's *last* rest, so F01's drop at
10 s fell outside it; and candidates came only from zone entries and exits, which F3's
margin removes for a vehicle that only noses up to the edge.

**Change.** (1) `_first_rest`: the window opens before the first of a chain of stops of
the same class in the same zone, each ending within the pre-margin of the next; events
carry track ids, not identities, so the chain is by class and place. (2) The
blocked-zone ranker considers every rest of the object in the window and adds
candidates from **contact**: a proximity event with the object that overlaps the
look-back before a rest, including a vehicle still withdrawing after setting it down.
Zone-entry candidates are kept. `incidents:…` config is unchanged; no new threshold.

**Results** (`post-golden-F7-2026-09-14.log`, F7-alone reasoning re-run; the first
reasoning run in that log loaded the detector with F4 already edited and its
detections-mode rows are superseded):

| Measure | Before | After |
|---|---|---|
| case_06 window | 14.1–44.9 s | **0.3–44.9 s** |
| case_06 perfect: ranked causes | none | **F01 (Possible), F02 (Likely contributed)**: both surfaced, F02 second |
| case_06 detections: ranked causes | none | F01 (Possible), a pallet fragment (Conflicting) — F02 is never detected (F1) |
| case_04 both modes | F01 first | F01 first, now also citing its contact with the pallet |
| Tune incidents and windows | — | unchanged |

Scene spec §6.6 asks that both be surfaced with scores and that F02 be no worse than a
close second; with perfect tracks that now holds. F01 outranks F02 because its contact
is 0.1 s from the first rest and F02's ends 1.3 s before the last; the ranking is by
timing, and the spec accepts either order.

**F7 amended after F4 (below) exposed a fragility.** The contact rule required the
proximity event's object to be in the trigger's identity group. When identity refuses to
join the object's per-camera tracks, the trigger's pallet (one camera) and the contact's
pallet (another) are different entities and no contact counts. The ranker now gathers
the object the way `detect_incidents` already does: every same-class track resting in
the zone while the trigger's does. Side effect on case_04 detections: the pallet
fragment that had been a second, *Conflicting* hypothesis is recognised as the object
and no longer ranked as a cause.

## F4 — a second box on a half-visible forklift

**Failure.** A forklift cut off by CAM_B's bottom edge got a box on the whole machine
and a second on its dark front face (IoU 0.27, under NMS). The second box seeded its own
track, and appearance linked that track to the real forklift on the other cameras: both
of case_02's false links.

**Change.** `nested_in_larger`: a box with at least 90% of its area inside a larger box
of the same class in the same frame is dropped (`…:nest0.9`). No case chose the value:
two objects of one class never nest in the image, and 0.9 is "nearly wholly inside".

**Results** (`post-golden-F4-2026-09-14.log`, all six cases, both modes):

| Measure | Before | After |
|---|---|---|
| case_02 forklift precision / recall | 0.687 / 0.980 | **0.986 / 0.980** (413 false boxes → 13) |
| case_02 CAM_B spurious boxes / ID switches | 417 / 2 | **17 / 1** |
| Tune detection, every class | Gate 1 values | unchanged to the third decimal |
| ID switches, worst camera, six cases | 2 | 1 |
| case_02 false links | 2 of 4 | **2 of 4**, on a different track |
| Tune false links / recall | 0 / 0.74 | 0 / 0.74 |

**What F4 did not fix.** The remaining false links join `CAM_B-T003` to F01. That track
is the forklift's front face detected *alone*, in frames where the rest of the machine
is outside CAM_B's view, so there is no larger box to nest in. It is a fragment of the
real forklift, and the links join it to that forklift on the other cameras, so no
trajectory between two real entities is invented; but the metric counts them and the
false-link rate on case_02 stays 0.50. A fragment at the frame edge is the visibility
limit accepted under F2, seen from the identity layer.

## F1 — a forklift of a colour the detector never saw

**Failure.** F02 is navy; the only forklift in the tune cases is F01, in another colour.
`yolo11n-rewind-v1` learned *forklift* as F01's colour and found F02 in 0 of 697 boxes.

**Change, time-boxed to one training run.** `yolo11n-rewind-v2`: the same recipe as v1
(`yolo11n.pt`, 20 epochs, seed 0, tune cases only, `case_05` for validation) with hue
jitter raised from Ultralytics' default of 0.015 to **0.5**, the full hue circle. That is
the one value that makes colour uninformative rather than merely varied, so no case chose
it. `scripts/ml/train_detector.py --hsv-h` records it in `training.json`.

**Results** (`artifacts/post-golden-F1-2026-09-14.log`, every harness, all six cases,
`REWIND_DETECTOR_CHECKPOINT` pointing at v2; v1 numbers are the F4 run on the same day
with the same F3–F7 code):

| Measure | v1 | v2 |
|---|---|---|
| Validation mAP50-95, `case_05` | 0.986 | 0.982 |
| Tune detection: person recall (case_01 / 03 / 05) | 0.998 / 0.979 / 0.989 | 0.998 / 0.981 / 0.976 |
| Tune detection: robot recall, forklift and pallet on case_04 | ≥ 0.989; 0.998 / 0.999 | ≥ 0.992; 1.000 / 0.999 |
| Tune ID switches, events, identity, incidents, causes | — | **identical to v1** in every row |
| case_06 forklift precision / recall | 0.908 / 0.259 | **0.981 / 0.938** — F02 is found on all three cameras |
| case_06 zone events, detections | 0.60 / 0.21 | 0.75 / 0.43 |
| case_06 detections: ranked causes | F01, a pallet fragment | **F01, F02**, F01 again, a pallet fragment: F02 in the top two (spec §6.6), every one *Conflicting* |
| case_06 cross-camera recall / false links | 0.38 / 0 | 0.08 / 0 |
| case_02 forklift precision / recall | 0.986 / 0.980 | 1.000 / **0.466** |
| case_02 person precision / recall | 0.875 / 0.065 | **0.257** / 0.056 |
| case_02 ID switches, worst camera | 1 | **3** (CAM_A and CAM_B; floor ≤ 2) |
| case_02 zone events, detections | 0.57 / 0.80 | 1.00 / 0.80 |
| case_02 false links / cross-camera recall | 2 of 4 (0.50) / 0.22 | 2 of 6 (0.33) / 0.40 |
| Golden zone events pooled, detections | 0.58 / 0.37 | 0.83 / 0.53 |
| Cause top-3 on five incidents, detections | 3 of 5 | **4 of 5** |
| Evidence coverage / unsupported claims, every report | 1.00 / 0.00 | 1.00 / 0.00 |

**What v2 fixed.** F02. Colour was the whole of the failure: with it removed from the
model's reach, the navy forklift is detected at 0.938 recall, tracked on every camera,
and ranked as a cause with real detections, which nothing before could do.

**What v2 broke, traced.** Per camera on case_02, v2 finds **0 of 449** forklift boxes
on CAM_B, where F01 stands cut off by the frame's bottom edge (the F4 view), and 48 of
its 52 false *person* boxes sit in frames whose only truth is that forklift: on CAM_A
three of F01's tracks flip class between *forklift* and *person*. v1 recognised the
truncated forklift by F01's colour. A colour-blind model has to know the shape, and no
tune case shows a forklift cut by a frame edge (case_04's F01 is always whole), so it has
never seen one. The regression is the colour shortcut being taken away from a view the
training data cannot teach by shape.

**Why F1 stops here.** A second run with a lower hue jitter would be chosen to bring
case_02's number back: tuning on a golden case. The fix that addresses both cases is
data, not training: a forklift of a second colour, or seen truncated, in a tune case
(E1 re-render; not in the time box). Whether v2 is promoted is an owner decision, taken
below.

**Promotion: v1 stays the worker default.** Owner decision, on the rule that also
decided identity refusal and F2: a guarantee that holds is never traded for progress on
one that does not. v1 passes case_02's ID-switch floor; v2 breaches it. v2 is kept as
measured (`ml/models/yolo11n-rewind-v2/`, no model card, never a default), because its
failure pattern says what fixes F1: not more colour augmentation, but a forklift of a
second colour or one seen truncated in the tune data. That is an E1 re-render, and the
next attempt at F1 once this record is closed.

## F2 — a person mostly hidden is not found: accepted, not fixed

**Failure.** On CAM_A, case_02's P01 stands behind the parked forklift at a median
visibility of 0.20; the detector finds 4 of 297 boxes (v1) or 3 (v2). Ground truth emits
a box at any visibility of 0.15 or more (scene spec §7), so the person-recall floor counts
those frames and fails at 0.065.

**Why it is not fixed.** Owner decision. Recall on a fifth of a silhouette is a detector
capability that the tune data neither contains nor could be made to contain without
changing the floor's meaning; a lower emission threshold in ground truth would move the
number, not the system. The design answer already exists: what a camera cannot usably
see is an *unseen interval*, and F6 now writes that interval as a *Cannot determine*
claim. On case_02 with real detections the gap is named at recall 1.00, so the report
is silent about nothing.

**What it costs.** Person recall and precision on case_02 stay under the floor, on every
detector; the false links of F4's fragment are the same limit seen from the identity
layer. The system's promise for such an interval is stated uncertainty, not detection.
Recorded in the charter's limitations and the ledger.

## Verdict: the golden pair after the fixes

Post-golden state = v1 detector with F3, F4, F6, F5 and F7 (`post-golden-F4-2026-09-14.log`,
reasoning from its F7-amended re-run). Held-out = EXP-0010. Pooled numbers add the tune
incidents as EXP-0010 did.

| Charter floor | Floor | Held-out (EXP-0010) | Post-golden | Moved by |
|---|---|---|---|---|
| Person detection recall / precision | ≥ 0.95 / ≥ 0.95 | 0.065 / 0.875 **FAIL** | 0.065 / 0.875 **FAIL** | — (F2 accepted) |
| Robot detection recall / precision | ≥ 0.95 | 0.991 / 0.998 PASS | 0.991 / 0.998 PASS | — |
| ID switches, worst camera | ≤ 2 | 2 PASS | **1** PASS | F4 |
| Zone events, real pipeline, P / R | ≥ 0.85 / ≥ 0.90 | 0.38 / 0.53 **FAIL** | 0.58 / 0.37 **FAIL** | F3 (precision up, edge touches lost) |
| Event timing error, max | ≤ 0.5 s | 0.40 s PASS | 0.40 s PASS | — |
| Cross-camera false-link rate | ≤ 0.05 | 0.25 (2 of 8) **FAIL** | 0.29 (2 of 7) **FAIL** | F4 moved the links to a fragment, did not remove them |
| Cross-camera recall | ≥ 0.65 | 0.35 **FAIL** | 0.29 **FAIL** | fewer forklift tracks to link after F4 |
| Evidence coverage, every report | ≥ 0.95 | 1.00 PASS | 1.00 PASS | — |
| Unsupported-claim rate | 0.00 | 0.00 PASS | 0.00 PASS | — |
| Gap recall | ≥ 0.90 | ≥ 0.995 PASS | ≥ 0.995 PASS | — |
| Cause top-3, detections, five incidents | 1.00 | 3 of 5 **FAIL** | 3 of 5 **FAIL** | F1 not promoted; v2 would give 4 of 5 |
| Cause top-1, detections | ≥ 0.67 | 0.60 **FAIL** | 0.60 **FAIL** | — |
| Cause top-1 / top-3, perfect tracks | (not a floor) | 0.80 / 1.00 | **0.80 / 1.00**, now with both golden causes ranked | F5, F7 |

| Behaviour the golden cases exist for | Held-out, perfect / detections | Post-golden, perfect / detections |
|---|---|---|
| C02.3 P01 hypothesis worded *Possible* | FAIL / FAIL | **PASS** / FAIL (P01 unseen after the gap, F2) |
| C02.4 *Cannot determine* claim citing the gap | FAIL / FAIL | **PASS / PASS** |
| C02.5 Not confidently wrong | PASS / false *Observed* claim | PASS / **PASS** |
| C06.2 F01 and F02 both ranked with scores | FAIL / FAIL | **PASS** / FAIL (F02 undetected, F1) |
| C06.3 F02 in the top two | PASS / FAIL | PASS (second) / FAIL |

**Reading.** Every reasoning-layer failure (F3, F5, F6, F7) is fixed, and with perfect
tracks both golden cases now behave as their spec asks. Nothing at the charter-floor
level changed verdict, because the floors that failed are perception floors, and the two
perception fixes were partial (F4) or not promoted (F1). The report side of the thesis,
that a reconstruction is evidence-traceable and says when it cannot know, holds on the
golden pair with real detections: coverage 1.00, unsupported 0.00, the unseen interval
named as a claim, and no false *Observed* statement left.

**What the golden pair still fails on, and where each goes.**

| Failure | Status | Next attempt |
|---|---|---|
| F1 navy forklift | v2 measured, not promoted | E1 re-render: a second forklift colour or a truncated forklift view in a tune case; retrain; measure |
| F2 hidden person | accepted limitation | none; the *Cannot determine* claim is the design answer |
| F4 fragment links | partial | identity refuses a track that is an edge fragment (short, at the frame edge, one camera): candidate rule, thresholds from tune cases |
| F3 cost on case_06 edge touches | accepted with F7 | a touch-and-reverse rule would be shaped on case_06; leave |

## F5 addendum — the fix did not reach the product path (found by the E9.4 golden e2e)

**Found.** `tests/e2e/test_golden_case.py` runs case_02 through `process_run` with
ray-cast boxes, so through the real tracker. P01 is unseen for 3.7 s and comes back as a
*new* track, first sighted already inside Z1 at 14.9 s: the event carries
`at_first_sight`, not `during_gap`. F5's rule bounded only `during_gap` events, so this
one was judged by its stamp, after the stop, and discarded. No *Possible: Person*
hypothesis on the path the product actually runs.

**Why no harness saw it.** `reasoning_on_detections.py`'s perfect mode labels every
observation with its true entity (`perfect_tracks`) and never runs the tracker, so P01
never fragments; detections mode runs the tracker but does not detect P01 after the gap
(F2). The one input that exercises this path, perfect boxes through the tracker, existed
only in the integration tests, and none of them used case_02. EXP-0011's "fixed" for F5
was true of the harness, not of the product.

**Change.** A first-sight entry is bounded by the incident window's start: nothing
before the window is in evidence, so the crossing happened at some moment between the
window's start and the first sighting. The description says so ("between 3.5 and 14.9 s
while no camera saw it"), the level stays capped at *Possible* by the existing bounded
rule, and the report's claim for such an event says "crossing not seen; first sighted
inside" instead of a time (`deterministic-0.2.1`). No new threshold.

**Results** (`post-golden-F5b-2026-09-14.log`, `reasoning-2026-09-14T182204Z`):

| Measure | Before | After |
|---|---|---|
| Harness, all ten rows (five incidents × two modes) | — | **identical** in ranking, level, gaps, claims, coverage |
| Golden e2e, tracked perfect boxes: person ranked | no | **yes, *Possible***, "between 3.5 and 14.9 s while no camera saw it" |
| Golden e2e: anything ranked above *Possible* | — | nothing |
| Golden e2e: person's rank | — | second, behind F01 (0.55 against 0.51) |

**What it does not do.** The person ranks second on the tracked path. Its crossing is
bounded only by the window, 11.4 s wide, so temporal precedence cannot prefer it over
F01's observed entry; the ranking is honest about that. Cause top-1 on this path is a
metric the harness cannot yet measure (above); the e2e pins the behaviours, not the rank.

**Owed.** A harness mode that runs ray-cast boxes through the tracker, so the product
path is measured, not only tested.

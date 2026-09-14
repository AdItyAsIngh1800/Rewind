# EXP-0011: Post-golden fixes for EXP-0010's failures

- **Date:** 2026-09-14
- **Status:** In progress. One section per fix, in the owner's order: F3, F6, F5, F7, F4, F1.
  F2 (a mostly hidden person) is accepted as a documented limitation, not fixed.

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

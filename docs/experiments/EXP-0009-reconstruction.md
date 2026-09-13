# EXP-0009: Reconstruction — evidence graph, ranked causes, gaps and report

- **Date:** 2026-09-13
- **Status:** Complete

| Field | Value |
|---|---|
| Hypothesis | Built from the incident window alone, the evidence graph (E7.1), uncertainty engine (E7.3), hypothesis ranker (E7.2) and deterministic report (E7.4) rank the annotated cause first on every tune incident, name the intervals nobody saw, and produce reports in which every claim cites evidence that exists |
| Dataset version | `v1`, per-actor colour render; tune incidents `case_01`, `case_03`, `case_04` (`case_05` opens none, EXP-0008); golden pair sealed |
| Preprocessing | Exactly what `process_run` stores: events merged by identity (EXP-0006/0007), telemetry, incidents (EXP-0008), then graph → hypotheses → report |
| Model / tracker version | `yolo11n-rewind-v1:native:conf0.25:iou0.5:edge16`, `bytetrack:buf30:match0.9:fps10`, `assoc:thr0.75:amb0.1:w0.35/0.4/0.25:gap15.0`, `evidence-0.1.0`, `uncertainty-0.1.0`, `hypotheses:tau5:look10:w0.35/0.3/0.2/0.15:strong0.7`, `deterministic-0.1.0` |
| Hyperparameters | None swept. Ranking weights set once from the scene spec's description of the flagship case, before any case was scored |
| Hardware | Apple M4, MPS |
| Config version | `v0.1.0` |

## Metrics

`reasoning-2026-09-13T155410Z`. Cause = the entity behind `cause_gt.json`, matched to a
hypothesis through the track segments its entity node was built from. Gaps in seconds
against `gaps_gt.json`, clipped to the window, per true entity, overlapping gap nodes
merged first.

| Case | Mode | Cause top-1 | Top level | Gap recall | Gap precision | Claims | Coverage | Unsupported | Graph nodes/edges |
|---|---|---|---|---|---|---|---|---|---|
| case_01 | perfect | P01 ✓ | strongly inferred | 1.00 | 1.00 | 5 | 1.00 | 0.00 | 20 / 31 |
| | detections | P01 ✓ | **conflicting** | 1.00 | 0.95 | 6 | 1.00 | 0.00 | 19 / 30 |
| case_03 | perfect | P01 ✓ | strongly inferred | — (no truth gap) | — | 5 | 1.00 | 0.00 | 20 / 34 |
| | detections | P01 ✓ | **conflicting** | — | 0.00 (8.0 s named) | 7 | 1.00 | 0.00 | 35 / 65 |
| case_04 | perfect | F01 ✓ | strongly inferred | 1.00 | 1.00 | 5 | 1.00 | 0.00 | 21 / 41 |
| | detections | F01 ✓ | strongly inferred | 1.00 | 0.98 | 10 | 1.00 | 0.00 | 28 / 58 |

**Totals:** cause top-1 6 of 6; evidence coverage 1.00 and unsupported-claim rate 0.00
in every report; gap recall 1.00 wherever truth has a gap. The largest graph is 35
nodes and 65 edges, far under the 10,000-node review trigger of ADR-0005.

Report summaries as issued, detections mode:

- case_01 — *Robot R12 reported an emergency stop at 13.4 s. Conflicting evidence: Person
  (CAM_A-T004, CAM_B-T002, CAM_C-T002) entered Z1 ROBOT_LANE at 12.8 s, 0.6 s before the
  robot's emergency stop.*
- case_04 — *Pallet stopped at 15.2 s and was still there when the dwell limit was crossed
  at 35.2 s. Likely contributed: Forklift (CAM_A-T001, CAM_B-T001, CAM_C-T001) entered Z2
  at 11.6 s and left at 16 s, around when the pallet came to rest there at 15.2 s.*

## Failure cases

| Case | What | Cause |
|---|---|---|
| case_01, case_03 detections | Flagship cause worded **Conflicting evidence**, not *Likely contributed* | The person's group joins three tracks through two links, while the direct comparison of two of them was refused (case_01: CAM_A-T004 ↔ CAM_C-T002 at 0.79, refused for ambiguity with a second CAM_A fragment; case_03: CAM_A-T002 ↔ CAM_B-T002 at 0.738, just under the threshold). That refusal's interval covers the approach, so it is held against the hypothesis. The evidence genuinely disagrees with itself; whether it should cap *this* hypothesis is the open question below |
| case_03 detections | 8.0 s of gap named on P02 where truth has none (precision 0.00) | P02's CAM_A and CAM_B tracks were never linked (0.42). Each is its own entity, so each is "unseen" while the other camera has it. The statement is true of what the system knows and false of the world; the identity conflict between the two tracks sits beside it in the graph |
| case_04 detections | A second hypothesis: a pallet track "entered Z2 and left" | A fragment of the same pallet that was not grouped with the stopped one became a candidate. Ranked second, worded *Conflicting evidence*, never promoted |
| Conflict node labels | Before this experiment, a refused pair inside one group read "CAM_A-T004 and CAM_A-T004" | Labelled by group id instead of track. Fixed (`fix: name both tracks in an identity conflict`) |

## Result

The reconstruction is right about **what** on every tune incident in both modes, and
every report is fully and truly cited. The residual disagreement is about **how
strongly** to say it: on real detections the flagship cause is under-claimed as
conflicting because the identity layer's own evidence is internally inconsistent over
the approach.

Both remaining errors lean the same way: the system says less than the truth, never
more. That is the direction the charter asks for, but a demo of C01 reading
"Conflicting evidence" is a real cost.

Untested here: the two behaviours the golden cases exist for. C02's UNKNOWN interval
over the critical moment is covered only by unit tests
(`test_a_gap_over_the_approach_caps_the_hypothesis_at_possible`), and C06's two
defensible causes have no tune-case counterpart. Both are measured at E9.1.

## Decision

**Adopt** the graph, ranker and generator as configured for Gates 4 and 5.
**Decided by the owner, 2026-09-13:** a refusal inside an identity group keeps capping
a hypothesis about that group (option A in `docs/gates/gate-4-5.md`), revisited only on
golden-case evidence. Not tuned here: two cases cannot tell a principled rule from one
fitted to them.

## Next experiment

E9.1 golden run: C02 must produce a POSSIBLE cause and a named gap over 11–15 s; C06
must surface both forklifts with scores.

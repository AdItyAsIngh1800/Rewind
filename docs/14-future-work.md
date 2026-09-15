# Future work

In the order it should be done. Each item names what it repays or what would trigger
it, so the list is a plan rather than a wish. Nothing here is started.

## 1. Owed — the debts the ledger still carries

*Closed 2026-09-15 (EXP-0013): the E1 re-render, the F1 retrain, and the postmortem's
verification date. `case_07` plus `yolo11n-rewind-v3` are in.*

| Item | Why | Size |
|---|---|---|
| **Tracker settings for F8 and F9**, tuned on `case_07` | The two behaviours EXP-0013 surfaced: a track carrying two entities in turn (invisible to the ID-switch metric) and a pushed pallet flipping between two tracks (4 switches against a floor of 2). `case_07` is a tune case containing both views | Half a day, plus a golden re-measure |
| **A harness measure for a track that carries two entities** | F8 has no number: `count_id_switches` counts an entity changing track, never a track changing entity. Until it does, a tracker fix cannot be scored | Half a day |
| **Tracked-perfect harness mode** — perfect boxes through the real tracker | Separates tracking loss from detection loss on the golden pair; EXP-0011 owed it when F5 was found by the e2e test and not the harness | Half a day |
| **Mentor walkthrough** of C01 with `docs/gates/gate-4-5-walkthrough.md` | The only human validation the plan scheduled; findings are post-golden | One session |
| **Reproducibility test by a stranger** from the README alone | Gate 6 was passed by the author twice; the roadmap asks for someone else | One afternoon of theirs |
| **Container CPU throughput** — 12–16 FPS in Docker against 63 FPS on the same CPU outside | Thread count and BLAS are the suspects; a usable batch tool at half real time made it a low priority | Half a day |
| **Golden benchmark in CI** | Spec §L "ML regression per release"; `make bench` exists, the rendered data is a private asset, CI would need `gh` access to fetch it | One afternoon |
| **Analytics trend and location** | `captured_at` is on the contract and null on simulated footage; incidents carry no zone. Set both at ingestion when real footage arrives | One day |

## 2. The stretch backlog, in the roadmap's order

1. **Public-footage realism check** (WILDTRACK, MMPTRACK). Highest evidential value:
   it is the only way to show the pipeline is not fitted to untextured primitives.
   Needs annotation of zones and a robot-telemetry stand-in; the harness is ready.
2. **LLM report layer**, strictly behind the deterministic template: a local quantised
   model consuming the evidence graph and hypotheses, the template retained as
   fallback, and a regression test that the LLM's unsupported-claim rate is 0.00
   against the template's. The evidence model was designed so this consumes structure,
   never frames.
3. **Re-ID embeddings** (OSNet or CLIP crops) beside the colour histogram, measured on
   the same identity harness. Motivated only if the realism check shows appearance is
   the limit; on simulated data the identity failures are geometric.
4. **Kafka or Redpanda** — only on one of `ADR-0010`'s four triggers, and Redis Streams
   first.
5. **Cloud deployment and OpenTelemetry** — after the split, not before.

## 3. Things the build revealed that the plan did not ask for

- **Fragment-aware identity.** The held-out false links joined a fragment of a real
  forklift, seen alone at the frame edge, to that forklift on other cameras. v3's
  cleaner boxes removed those links (EXP-0013), but not the gap they exposed: the layer
  still has no way to say "this track is part of an entity I already know" rather than
  "this is a new entity". F8, where one track carries two forklifts in turn, is the
  same gap seen from the tracker. The graph's `occludes` edge is the natural home.
- **A visibility floor for detection targets, separate from the ground-truth floor.**
  Ground truth emits boxes from 15 % visibility for gap precision; detection recall
  should be scored from a higher floor, with the band between reported as *unseen*,
  the way events already report bounded truth.
- **An appearance-coverage table at E1.3**, before sealing golden cases: entity
  colours, visibility distribution, camera coverage per case. The postmortem's
  preventive action.
- **A dead-letter queue.** `/metrics` reports retries and failures from the worker's
  heartbeat; a run that fails three times is FAILED with a reason, but nothing lists
  the jobs arq gave up on. Small, and the System Health screen has the tile for it.

## 4. Not planned

Face recognition, by charter and by the statement on every report. Live RTSP
ingestion until `ADR-0010` trigger 4 lifts the non-goal. A third role. A graph
database. Training a detector from scratch.

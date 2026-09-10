# 00 — Project Charter

- **Project:** REWIND — evidence-backed AI incident reconstruction for multi-camera video
- **Charter date:** 2026-09-09
- **Builder:** solo, ~15–20 h/week
- **Duration:** 20 weeks · Week 0 begins 09 Sep 2026 · delivery week ends Tue 02 Feb 2027
- **Status:** Scope frozen

---

## 1. The one sentence

REWIND converts multiple camera streams into structured entities and events,
synchronizes them onto a shared timeline, detects an incident, rewinds the window
around it, and reconstructs what happened — marking every claim with the strength of
evidence behind it, including when the evidence proves nothing.

## 2. Why this is not a video classifier

A classifier can say *an anomaly occurred*. It cannot show the sequence, connect
evidence across views, or admit what it could not see. The engineering interest of this
project lives entirely in the second half of that sentence.

## 3. Scope freeze

These numbers are frozen. Changing any of them requires an ADR and a deviation-ledger
row classified `SCOPE-CREEP`.

| | Frozen value |
|---|---|
| Cameras | **3** |
| Scenes | **1** (simulated warehouse) |
| Rendered incident cases | **6** — 4 for tuning, 2 held out as golden |
| Incident classes | **2** |
| Entity classes | **4** — `person`, `robot`, `forklift`, `pallet` |
| Video envelope | 720p, 10 FPS |

### The two incident classes

1. **`ROBOT_ESTOP_HUMAN_INCURSION`** — a robot performs an emergency stop after a
   person enters its planned path. This is the flagship case: it requires cross-camera
   identity, temporal precedence and trajectory convergence to reconstruct, which is
   the full thesis in one incident.
2. **`ZONE_BLOCKED_UNATTENDED_OBJECT`** — a pallet or forklift is left obstructing a
   designated keep-clear zone beyond a dwell threshold. Deliberately simpler; it
   exercises the same pipeline with a single-entity trigger, so it is the fallback that
   still satisfies the Definition of Done if class 1 proves too hard to reconstruct.

### At least one case must produce a genuine UNKNOWN

One rendered case occludes the critical interval from every camera that could have
proven contact. The system must report *cannot determine* rather than inferring
a collision. **This is a feature under test, not an edge case** — a build that cannot
produce an honest UNKNOWN has failed its central claim.

## 4. Non-goals

Written down so they can be pointed at in Week 12 when they start sounding reasonable.

- Face recognition — permanently out of scope, not merely deferred.
- Live RTSP or real-camera ingestion.
- Training a detector or tracker **from scratch** — random initialisation, large
  external datasets, detector research. **Fine-tuning a pretrained detector on our own
  synthetic data is explicitly in scope** and is not this; see `ADR-0004`.
- Kafka, an event bus, or any service split (see `ADR-0001`).
- Multi-tenant authentication or user management.
- Cloud deployment as a requirement.
- Mobile or responsive-first UI.
- More than three cameras, more than one scene, more than two incident classes.

## 5. Definition of Done

Copied verbatim from the master specification §P. Each line is a gate on delivery, not
an aspiration.

- [ ] 1. Three camera clips can be ingested and processed
- [ ] 2. Detection and tracking meet the benchmark threshold *(threshold set at Gate 1 — see §6)*
- [ ] 3. Events are timestamped and queryable
- [ ] 4. At least one incident class is automatically detected
- [ ] 5. An investigation window is created automatically
- [ ] 6. Cross-camera evidence is assembled
- [ ] 7. Evidence graph is generated
- [ ] 8. Cause hypotheses are ranked
- [ ] 9. Unknown and occluded intervals are explicit
- [ ] 10. Investigator UI supports replay and timeline inspection
- [ ] 11. Report is evidence-grounded
- [ ] 12. Critical logic has automated tests
- [ ] 13. Benchmark results and failure cases are documented
- [ ] 14. Repository can be started from the README
- [ ] 15. Architecture, ML, security, evaluation and deployment documentation are complete

## 6. Benchmark thresholds — provisional

DoD line 2 requires a threshold. Setting a defensible number before measuring anything
would be theatre, so these are **provisional floors** to be replaced at Gate 1 by
values calibrated against the measured baseline. A floor may be lowered only with an
experiment record showing why it was unreachable.

| Metric | Provisional floor | Rationale |
|---|---|---|
| Detection recall (person, robot) | ≥ 0.90 | Synthetic data with controlled lighting; missing the incident participants is fatal |
| Detection precision | ≥ 0.85 | False entities manufacture evidence |
| ID switches per case, per camera | ≤ 2 | Cross-camera identity cannot repair broken single-camera tracks |
| Event timing error | ≤ 0.5 s | Below the temporal resolution a human investigator would dispute |
| Cross-camera **false-link rate** | ≤ 0.05 | The one metric where being wrong is worse than being silent |
| Evidence coverage | ≥ 0.95 | Every material claim carries a reference |
| Unsupported-claim rate | 0.00 | Structural, not statistical — the generator raises rather than emits |

## 7. Locked technical decisions

| Decision | Choice | Record |
|---|---|---|
| Dataset | Simulated, authored in Blender | §3 above |
| Architecture | Modular monolith, containerized | `ADR-0001` |
| Report generation | Deterministic template; LLM is stretch only | spec §D3 |
| Detection | `yolo11n` fine-tuned on the four tuning cases. The zero-shot figure is reported but is uninformative while entities are primitives | `ADR-0004` |
| Accelerator / environment | Apple M4, 16 GB unified memory, Metal/MPS | `docs/09-deployment.md` |
| Database / storage / auth | Supabase (hosted Postgres, Storage, Auth + RLS, pgvector) | `ADR-0003` |
| Licence | AGPL-3.0 (inherited from Ultralytics) | `ADR-0002` |
| Hosting | Private GitHub repo; public at delivery | `ADR-0002` |

## 8. Gate calendar

| **Gate 1** | E3.4 | Video reliably becomes timestamped observations | Week 7 | **Tue 03 Nov 2026** |
| **Gate 2** | E4.4 | Observations become correct semantic events | Week 9 | **Tue 17 Nov 2026** |
| **Gate 3** | E5.4 | Events can be connected across cameras | Week 11 | **Tue 01 Dec 2026** |
| **Gate 4** | E7.5 | An incident can be reconstructed without an LLM | Week 14 | **Tue 22 Dec 2026** |
| **Gate 5** | E7.5 | Every conclusion is evidence-traceable | Week 14 | **Tue 22 Dec 2026** |
| **Gate 7** | E9.1 | Benchmark results and failure modes are measurable | Week 17 | **Tue 12 Jan 2027** |
| **Gate 6** | E10.1 | A new developer can run the system from the repository | Week 19 | **Tue 26 Jan 2027** |

## 9. Milestones

| When | Milestone | Ends |
|---|---|---|
| Week 0 | Pre-start checklist complete | Tue 15 Sep 2026 |
| Week 3 | M1 — six rendered cases with ground truth | Tue 06 Oct 2026 |
| Week 4 | M2 — reproducible hashed processing runs | Tue 13 Oct 2026 |
| Week 12 | M6 — incident auto-creates a case | Tue 08 Dec 2026 |
| Week 16 | M8 — end-to-end workflow in a browser | Tue 05 Jan 2027 |
| Week 20 | Final audit and delivery | Tue 02 Feb 2027 |

## 10. How this charter gets used

When a new idea arrives mid-build, it is checked against §4. If it is a non-goal, it
goes to the post-MVP backlog without discussion. If it is not, it still needs a
deviation-ledger row before any code is written.

The single most likely failure mode of this project is not technical difficulty. It is
spending weeks 13 and 14 — which carry the entire argument — on something that felt
more interesting at the time.

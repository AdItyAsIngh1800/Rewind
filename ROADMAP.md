# REWIND — Build Plan & Roadmap

## Context

`REWIND_Master_Project_Engineering_Specification.docx` defines an evidence-backed AI incident
reconstruction engine for multi-camera video. The spec is complete on *what* to build (563 lines:
functional requirements, schema, API contract, evaluation protocol, DoD) but contains no execution
plan — its own timeline table is internally inconsistent (header says 20 weeks, table spans 7) and
its phases P0–P7 are strictly sequential, so any slip cascades.

The working directory contains only the `.docx`. This is greenfield.

**This plan converts the spec into an executable roadmap with three properties the spec lacks:**

1. **Contract-first decoupling.** All schemas, the API surface, and *golden fixture files at every
   boundary* are frozen in the pre-phase. Every execution sub-phase then reads a fixture, not the
   previous phase's live output. A sub-phase can therefore be built, tested and finished even when
   its upstream neighbour is incomplete or broken. This is the single mechanism that stops the
   dependency cascade.
2. **Atomic sub-phases.** Each has one deliverable, one exit artifact, and an explicit prerequisite
   that is a *file*, not a *phase*.
3. **A drift ledger.** Deviation from this plan is expected and often correct; the post-phase
   classifies each deviation as improvement / neutral / debt rather than pretending it didn't happen.

### Decisions locked (from your answers)

| Decision | Choice | Consequence |
|---|---|---|
| Budget | **20 weeks**, solo | ~15–20 h/week assumed. Weeks 17 and 20 are deliberate slack. |
| Dataset | **Simulated (Blender)** | Perfect ground truth, exact timestamps, repeatable incidents, zero privacy/licensing risk. Public-footage realism check deferred to stretch. |
| Production depth | **Modular monolith, containerized** | Kafka / service split / AWS / OTel are *not* on the critical path. An ADR records why. Stretch only if Gates 1–6 clear early. |
| Report layer | **Deterministic template committed** | Spec §D3 requires the engine to work without an LLM. LLM report is a Week 19 stretch (assumption — flag if you want it promoted to core). |

### Non-goals (write these into the charter and defend them)

Face recognition · live RTSP ingestion · training a detector from scratch · Kafka/microservices ·
multi-tenant auth · cloud deployment · mobile UI · more than 3 cameras · more than 2 incident classes.

---

# PART 1 — PRE-START PHASE (Weeks 0–1)

Nothing in Part 2 begins until Part 1 is done. These sub-phases are mutually independent except
where noted — **PS-4 is the keystone** and gates the execution phase.

| ID | Sub-phase | Depends on | Output artifact | Time |
|---|---|---|---|---|
| PS-1 | Scope freeze & charter | — | `docs/00-project-charter.md` | 0.5 d |
| PS-2 | Hardware & environment baseline | — | `docs/09-deployment.md` §env, `scripts/bootstrap/` | 1 d |
| PS-3 | Repo skeleton + docs system + CI | — | Repo tree, green CI badge | 1 d |
| PS-4 | **Contract freeze** | PS-3 | `packages/schemas/`, `docs/04-data-contracts.md`, `openapi.json` | 2 d |
| PS-5 | **Golden fixtures + mock API** | PS-4 | `tests/fixtures/golden/`, `scripts/mock_api.py` | 1 d |
| PS-6 | Scene & incident design | — | `docs/dataset/scene-spec.md`, storyboard | 1 d |
| PS-7 | Evaluation harness stub | PS-4 | `packages/evaluation/`, `docs/07-evaluation-plan.md` | 1 d |
| PS-8 | Design language decision | — | `docs/ui/design-tokens.md`, `web/src/styles/tokens.css` | 1 d |
| PS-9 | Risk register + gate calendar | PS-1 | `docs/risk-register.md` | 0.5 d |

### PS-1 · Scope freeze & charter
**Decide, don't discover.** Answer in writing and stop revisiting:
- Exactly **2 incident classes** for MVP (recommend: *robot emergency stop triggered by human entering
  path*, and *unattended-object / route-blocked*). Everything else is post-MVP backlog.
- Exactly **3 cameras**, exactly **1 scene**, exactly **6 rendered incident cases** (4 train/tune,
  2 held-out golden).
- Entity classes: `person`, `robot`, `forklift`, `pallet`. Four. Not five.
- Definition of Done copied verbatim from spec §P into the charter, each line given an owner-check box.

**Exit:** charter signed off by you and your mentor. **Links to:** everything — this is the document
you point at when you're tempted to add a feature in Week 12.

### PS-2 · Hardware & environment baseline
- Pin `PyTorch` + CUDA wheel *after* checking current official compatibility against your installed
  NVIDIA driver (spec §H flags this explicitly — don't copy a version from a blog post).
- Run a VRAM smoke test: YOLO inference at 720p, batch 1/2/4, record peak VRAM in a table. **Your
  6 GB budget is the constraint that shapes every later ML decision** — knowing the real number now
  prevents a Week 9 discovery.
- `uv` project init, lockfile committed.
- Record the numbers in `docs/09-deployment.md`. Note the operating envelope: 720p, 5–10 FPS, one
  heavy GPU workload at a time.

**Exit:** `uv run scripts/bootstrap/smoke_gpu.py` prints a VRAM table on a clean clone.

### PS-3 · Repo skeleton + docs system + CI
- Create the tree from spec §I. **Create it empty with `.gitkeep` and a one-line `README.md` in each
  directory explaining what belongs there** — an unexplained empty folder is worse than no folder.
- Docs system live from day one: ADR template (§O2), experiment template (§O3), weekly log (§O4),
  postmortem template (§O5). Write **ADR-0001: modular monolith over microservices** immediately —
  it's the decision you already made, and having ADR-0001 exist makes ADR-0002 easy to write.
- GitHub Actions: ruff + mypy + pytest on push. It runs zero real tests today. That's fine — the point
  is the gate exists before there's anything to gate.
- `Makefile` targets: `make dev`, `make test`, `make bench`, `make render`.

**Exit:** clean clone → `make dev` → green CI.

### PS-4 · CONTRACT FREEZE ★ keystone
This is the highest-leverage half-day of the project.

Define, in `packages/schemas/` as Pydantic v2 models, with a `schema_version` field on each:
- `Observation`, `TrackSegment`, `IdentityLink`, `SemanticEvent`, `Incident`, `EvidenceNode`,
  `EvidenceEdge`, `Hypothesis`, `Report`, `ProcessingRun` — fields per spec §E1.
- The **internal event envelope** per spec §F: `event_id, schema_version, event_type, event_time,
  entity_ids, source_camera, producer_service, producer_version, confidence, evidence_refs, payload`.
- The **evidence level enum** — `CONFIRMED | STRONGLY_INFERRED | POSSIBLE | CONFLICTING | UNKNOWN`
  (spec §6) — and the allowed-language mapping, as data not prose.
- Postgres DDL via SQLAlchemy 2.0 + first Alembic migration. JSONB for evidence/config blobs.
- Generate `openapi.json` from a FastAPI app whose endpoints (spec §F) all return `501` for now.

**Why this gates everything:** after this, sub-phase N+1 is written against a *type*, and its tests run
against a *fixture*. It never waits for sub-phase N to work.

**Exit:** `openapi.json` committed; `alembic upgrade head` builds an empty DB; schema round-trip test passes.

### PS-5 · Golden fixtures + mock API ★ the decoupler
Hand-author (or script) one small, valid JSON file for **every** contract boundary, describing one
complete toy incident:

```
tests/fixtures/golden/
  01_run.json            10_observations.json    20_track_segments.json
  30_identity_links.json 40_events.json          50_incident.json
  60_evidence_graph.json 70_hypotheses.json      80_report.json
```

Then `scripts/mock_api.py` — a ~40-line FastAPI app serving those files at the real endpoints.

**Payoff:** the frontend (E8) can start in Week 4 against the mock and never blocks on the ML pipeline.
Every backend sub-phase gets a ready-made input and a ready-made expected output. If a sub-phase's real
output diverges from its fixture, you've found a contract bug, not a code bug — and you found it in
minutes.

**Exit:** `make mock` serves all 8 endpoints; frontend can `fetch` from it.

### PS-6 · Scene & incident design
- Choose **Blender** (free, scriptable in Python, exact camera intrinsics/extrinsics, frame-accurate
  ground truth export). Alternatives noted in an ADR: Unity Perception, NVIDIA Omniverse Replicator, CARLA.
- Storyboard the 2 incident classes on paper: actor paths, camera placements, and **deliberate occlusion**
  (one camera must lose the critical moment — the UNKNOWN state is a headline feature and needs a case
  that actually produces it).
- Define the ground-truth export format *now* and make it conform to the PS-4 `Observation` schema.
  Ground truth and predictions in the same shape is what makes the evaluation harness trivial.

**Exit:** `docs/dataset/scene-spec.md` with camera positions, zone polygons, actor scripts, and the
expected ground-truth timeline for each of the 6 cases, written by hand before anything is rendered.

### PS-7 · Evaluation harness stub
- Implement metric functions against fixtures only: precision/recall, ID-switch count, IDF1 (via
  `motmetrics`), event F1 + timing error, cause-ranking top-k, **evidence coverage**, **unsupported-claim
  rate**.
- The last two are the project's thesis. Define them precisely now:
  - *Evidence coverage* = (material claims in report with ≥1 valid evidence_ref) / (material claims).
  - *Unsupported-claim rate* = claims whose evidence_refs don't actually support the stated evidence level.
- `make bench` runs against fixtures and emits `artifacts/benchmark-reports/<date>.md`. It reports
  perfect scores today because it's scoring the fixture against itself. That's the correct starting state.

**Exit:** `make bench` produces a report file. Every later phase adds real numbers to the same table.

### PS-8 · Design language decision
Decide before writing one component (details and source links in **Part 4**):
- **Dark-first**, low-chroma neutral base — this is an operator/investigator tool viewed for long
  sessions, not a marketing site.
- **Evidence-state visual encoding** — the one thing this UI must get right. Encode on **three
  independent channels**, never colour alone:

  | State | Colour | Pattern | Label |
  |---|---|---|---|
  | Confirmed | high-contrast solid | solid fill / solid stroke | "Observed" |
  | Strongly inferred | mid | dashed stroke | "Likely contributed" |
  | Possible | low | dotted stroke | "Possible" |
  | Unknown | desaturated grey | diagonal hatch | "Cannot determine" |
  | Conflicting | warning hue | cross-hatch | "Conflicting evidence" |

  Verify every pair at 4.5:1 contrast and under deuteranopia/protanopia simulation. **This is
  accessibility, not polish — do not defer it.**
- Fix type scale, spacing scale, radius, and the token file. Commit as CSS custom properties so the
  Tailwind config and any chart library read from one source.

**Exit:** `docs/ui/design-tokens.md` + a single static HTML swatch page showing all evidence states
side by side, contrast-checked.

### PS-9 · Risk register + gate calendar
Copy spec §K's 16 challenges into `docs/risk-register.md` with columns: *risk · likelihood · impact ·
early-warning signal · mitigation · trigger-to-escalate*. Put the 7 milestone gates (spec §J) on
calendar dates. A gate with no date is a wish.

---

## Pre-start exit checklist

- [ ] Charter frozen, non-goals written down
- [ ] GPU envelope measured, versions pinned, lockfile committed
- [ ] Repo tree + docs templates + green CI
- [ ] **Schemas frozen, migration runs, `openapi.json` generated**
- [ ] **Golden fixtures exist for all 8 boundaries; mock API serves them**
- [ ] Scene + 2 incidents + occlusion case storyboarded, ground-truth format = Observation schema
- [ ] `make bench` runs
- [ ] Design tokens + evidence-state encoding, contrast-verified
- [ ] Risk register + 7 gate dates on calendar

---

# PART 2 — EXECUTION PHASE (Weeks 2–19)

Each sub-phase below states: **Goal · Tasks · Result · Prerequisite · Link forward.**
Note that every *Prerequisite* is an artifact, not a phase.

## E1 · Data Foundation — Weeks 2–3
> **Milestone M1:** 6 rendered incident cases with frame-exact ground truth, versioned and checksummed.

| | |
|---|---|
| **E1.1 Scene build** | **Goal:** a Blender warehouse with 3 cameras and 4 entity types. **Tasks:** model/asset the scene (use free CC0 assets — don't model a forklift by hand); place 3 cameras with overlapping-but-not-identical coverage; define zone polygons in world coordinates matching PS-6. **Result:** `.blend` file + camera calibration JSON. **Prereq:** `docs/dataset/scene-spec.md`. **Links to:** E1.2 consumes the scene. |
| **E1.2 Incident rendering + ground truth** | **Goal:** 6 cases rendered from 3 views each with per-frame ground truth. **Tasks:** script actor paths in Blender Python; render at 720p/10 FPS; **export ground truth in the PS-4 `Observation` schema** (bbox, class, track id, world position, per camera, per frame) plus a ground-truth `SemanticEvent` timeline; deliberately occlude the critical interval in ≥1 case. **Result:** `data/samples/case_{01..06}/` — 18 video files + GT JSON. **Prereq:** E1.1 `.blend`. **Links to:** replaces `10_observations.json` fixture with real GT — every downstream phase now has a real target. |
| **E1.3 Dataset manifest & versioning** | **Goal:** reproducibility. **Tasks:** manifest with source, license, version, checksum per file (spec §E2); `dataset_version` string that goes into every `ProcessingRun`; split 4 tune / 2 **held-out golden** — and *do not look at the golden 2 until Week 16*. **Result:** `data/manifests/v1.json`. **Prereq:** E1.2. **Links to:** the evaluation harness (PS-7) now scores against real GT. |

**Progress target end of Week 3:** `make bench` scores ground truth against ground truth and reports
1.0 across the board — proving the harness plumbing is correct before any model exists.

## E2 · Ingestion & Run Registry — Week 4 (½ week)
> **Milestone M2:** any video set becomes a reproducible, hashed processing run.

| | |
|---|---|
| **E2.1 Video ingestion** | **Goal:** video → deterministic sampled frames + metadata. **Tasks:** ffmpeg/OpenCV probe for FPS/resolution/duration/timestamps; **deterministic** frame sampling (same input ⇒ same frames, always); timestamp normalization with per-camera offset config. **Result:** `services/ingestion/`. **Prereq:** `Camera` + `ProcessingRun` schemas. **Links to:** E3 consumes sampled frames. |
| **E2.2 Run registry** | **Goal:** spec §B2 reproducibility. **Tasks:** input hash + dataset version + model versions + config version persisted per run; job created in Redis-backed queue (ARQ); job is **idempotent and retryable**. **Result:** `POST /api/v1/cases` creates a real run. **Prereq:** Alembic migration. **Links to:** every later stage stamps its output with `run_id`. |

**Note:** run the pipeline stages sequentially in-process for now (spec §11). Do not parallelize
anything until profiling in E9.3 says to.

## E3 · Perception — Weeks 5–7
> **GATE 1 — video reliably becomes timestamped observations.**

| | |
|---|---|
| **E3.1 Detection baseline + fine-tune** | **Goal:** a scored detector covering all four entity classes. **Tasks:** (a) record the COCO zero-shot baseline — `person` only, since `robot` and `pallet` are not COCO classes (`ADR-0004`); (b) fine-tune `yolo11n` on 3 tuning cases, validate on the 4th, golden cases untouched; (c) measure precision/recall/mAP/FPS/memory for **both** models side by side. **Log every run as an experiment record (§O3) from the very first one** — the registry is worthless if you start it in Week 10. **Result:** first real numbers in the benchmark report. **Prereq:** sampled frames (E2.1) *or* just decode video directly — this phase does not require E2.2. **Links to:** E3.2. |
| **E3.2 Single-camera tracking** | **Goal:** stable per-camera track IDs. **Tasks:** ByteTrack per camera; measure ID switches + IDF1 against GT; tune track buffer / match threshold. **Result:** `TrackSegment` records. **Prereq:** detections (E3.1) *or* the GT observations as a perfect-detector stand-in — **you can build and test tracking with a fake detector**. **Links to:** E4 consumes trajectories. |
| **E3.3 Observation persistence** | **Goal:** the DB stops being empty. **Tasks:** bulk-write observations + track segments; index on `(run_id, camera_id, timestamp)`; verify a timestamp-range query returns in <500 ms locally. **Result:** queryable observation store. **Prereq:** migration + `TrackSegment` schema. **Links to:** everything downstream reads from here instead of re-processing video (spec §11). |
| **E3.4 Gate 1 review** | Detection + tracking benchmark report, failure cases catalogued with screenshots, model card v1 written. **If ID-switch rate is unusable, stop and fix here** — E5 cross-camera identity cannot rescue broken single-camera tracking. |

**Progress target end of Week 7:** benchmark table has real detection + tracking numbers with a
documented baseline. Gate 1 signed.

## E4 · Event Engine — Weeks 8–9
> **GATE 2 — observations become correct semantic events.**

| | |
|---|---|
| **E4.1 Geometry primitives** | **Goal:** pure, tested spatial functions. **Tasks:** point-in-polygon, zone entry/exit edge detection, proximity, dwell, direction change, speed. **All pure functions, all unit-tested, zero I/O.** **Prereq: NONE — this sub-phase has no dependencies at all and can be built in Week 1 if you're blocked elsewhere.** **Result:** `packages/common/geometry.py` at ~100% unit coverage. **Links to:** E4.2. |
| **E4.2 Semantic event extraction** | **Goal:** trajectories → `SemanticEvent`s. **Tasks:** emit zone entry/exit, stop, direction change, proximity, occlusion, state change; attach confidence and `evidence_refs` back to source observations; **occlusion events are first-class**, not an error case. **Result:** event stream per case. **Prereq:** `20_track_segments.json` fixture — real tracking not required. **Links to:** E4.3, E6. |
| **E4.3 Timeline store + query** | **Goal:** searchable timeline. **Tasks:** persist events; `GET /cases/{id}/timeline` returns real data (mock API's first endpoint retired). **Result:** live endpoint. **Prereq:** event schema. **Links to:** frontend E8.3 swaps mock → real for this endpoint only. |
| **E4.4 Gate 2 review** | Event precision/recall/F1 + timing error vs GT event timeline. Failure cases documented. |

**Progress target end of Week 9:** you can query "what happened in camera B between 10:32:00 and
10:33:00" and get semantically correct answers.

## E5 · Multi-Camera Identity — Weeks 10–11
> **GATE 3 — events connect across cameras.** *Highest-risk technical phase.*

| | |
|---|---|
| **E5.1 Temporal alignment** | **Goal:** one shared clock. **Tasks:** normalize to a common timebase; configurable per-camera offset; **a synchronization test that deliberately injects a 500 ms offset and asserts detection**. **Result:** aligned timestamps. **Prereq:** camera metadata. **Links to:** E5.3 scoring. |
| **E5.2 Appearance features** | **Goal:** comparable entity descriptors. **Tasks:** start with the *cheap baseline* — colour histogram + bbox aspect + size. Measure it. Only then try an embedding model (OSNet / CLIP crop embedding) and **report both numbers side by side** (spec §D4: every advanced method compared against a simpler baseline). **Result:** feature extractor + comparison table. **Prereq:** track segments. |
| **E5.3 Association & the UNKNOWN decision** | **Goal:** link segments across cameras *or refuse to*. **Tasks:** score = f(time overlap, appearance similarity, geometric plausibility); threshold into `LINKED` / `UNKNOWN`; **refusing to link must be a normal outcome, not a failure** — measure false-link rate as the primary metric, not just recall. **Result:** `IdentityLink` records with scores and evidence refs. **Prereq:** E5.1 + E5.2. **Links to:** E7 evidence graph edges. |
| **E5.4 Gate 3 review** | Cross-camera precision / recall / **false-link rate** vs GT identities. A high false-link rate is worse than low recall for this project — it manufactures evidence. |

**Risk note:** if cross-camera linking underperforms by Week 11, **do not extend this phase**. Ship it
with a conservative threshold that produces more UNKNOWNs, document the limitation, and move on.
An honest UNKNOWN is on-thesis; a late schedule is not.

## E6 · Incident Detection & Investigation Window — Week 12
> **Milestone M6:** an incident auto-creates a case with a rewind window.

| | |
|---|---|
| **E6.1 Incident triggers** | **Goal:** detect the 2 MVP incident classes deterministically. **Tasks:** rule-based triggers over the event stream (robot stop state change; zone violation); severity assignment; measure precision/recall/false-alert-rate/lead-time. **Result:** `Incident` records. **Prereq:** `40_events.json` fixture. **Links to:** E6.2. |
| **E6.2 Rewind orchestration** | **Goal:** the "rewind" the product is named for. **Tasks:** configurable pre/post window; gather all events + observations + clip references in window across all 3 cameras; create the case; transactional (spec §N). **Result:** `GET /cases/{id}` returns a real case. **Prereq:** incident record. **Links to:** E7 consumes the window contents. |

## E7 · Evidence Graph & Reasoning — Weeks 13–14
> **GATE 4 — an incident is reconstructed without an LLM.**
> **GATE 5 — every conclusion is evidence-traceable.**
> *This phase is the project's thesis. Protect its schedule above all others.*

| | |
|---|---|
| **E7.1 Evidence graph builder** | **Goal:** provenance-carrying graph. **Tasks:** nodes = entities/observations/events/locations/time-intervals; edges = temporal, spatial, causal-candidate, identity; **every node and edge carries `provenance` pointing at a concrete source ref**; store in Postgres (recursive CTE traversal — no graph DB needed at this scale, record as an ADR). **Result:** `GET /cases/{id}/evidence`. **Prereq:** `50_incident.json` fixture. **Links to:** E7.2 + E7.3 + the UI graph view. |
| **E7.2 Hypothesis generation & ranking** | **Goal:** ranked candidate causes, never a single asserted cause. **Tasks:** enumerate candidate contributing causes from graph patterns; score on temporal precedence + spatial proximity + evidence strength + trajectory convergence; attach `support_refs` **and `contradiction_refs`**; measure top-1/top-k vs annotated causes. **Result:** `Hypothesis` records. **Prereq:** evidence graph. **Links to:** report + hypothesis panel. |
| **E7.3 Uncertainty engine** | **Goal:** make gaps explicit and first-class. **Tasks:** detect occluded intervals, conflicting observations, low-confidence links, and **intervals no camera covers at all**; emit them as graph nodes so they render in the UI and appear in the report. **Result:** gap/conflict nodes. **Prereq:** graph + identity links. **Links to:** Evidence Gap View, and the report's limitations section. |
| **E7.4 Deterministic report generator** | **Goal:** an evidence-grounded report with no LLM. **Tasks:** template renders confirmed observations → inferences → ranked hypotheses → **explicit uncertainty section**; language strictly bound to the evidence-level enum from PS-4 ("Observed" / "Likely contributed" / "Possible" / "Cannot determine"); **every material claim emits an evidence ID or the generator raises**. **Result:** `GET /cases/{id}/report`. **Prereq:** hypotheses + gaps. **Links to:** Report View; this is the LLM-free fallback the whole anti-hallucination story rests on. |
| **E7.5 Gates 4 & 5 review** | Evidence coverage ≥ 95%, unsupported-claim rate ≈ 0 (the generator should make it structurally impossible). Walk a full case end to end with your mentor. |

**Progress target end of Week 14:** `POST /cases` → wait → `GET /cases/{id}/report` produces a
readable, correct, fully-cited incident reconstruction. **At this point the project is defensible even
if nothing else ships.**

## E8 · Investigator UI — Weeks 4–16 (interleaved)
> **Milestone M8:** end-to-end investigator workflow in a browser.

**This phase runs against the mock API from Week 4 and has no dependency on the ML pipeline until
E8.6.** Do ~1 day/week of UI from Week 4 onward; it becomes the primary focus in Weeks 15–16. This
interleaving is what makes 20 weeks feasible solo, and it de-risks the spec's own warning that the
frontend is a time sink (§K).

| | |
|---|---|
| **E8.1 Shell + Case Inbox** *(Wk 4–5)* | Vite + React + TS + Tailwind + shadcn/ui; design tokens from PS-8; TanStack Query; inbox filtered by severity/time/location/status. **Prereq:** mock API. |
| **E8.2 Synchronized replay** *(Wk 6–8)* | **Build this second — it is the hardest UI problem and the core product interaction.** 3 `<video>` panes on one shared timeline clock; scrub seeks all three; `requestVideoFrameCallback` for frame-accurate sync; handle differing durations/offsets. **Prereq:** replay metadata fixture. |
| **E8.3 Timeline tracks** *(Wk 9–10)* | Entity and event lanes aligned to timestamps; **clicking an event seeks all cameras to that timestamp** (spec §G, the defining interaction); occluded intervals rendered with the PS-8 hatch pattern. **Prereq:** timeline endpoint (real by E4.3). |
| **E8.4 Evidence graph view** *(Wk 11–12)* | React Flow (or Cytoscape); nodes styled by evidence state per PS-8; click node → seek video + highlight timeline. Keep layout simple — polish is explicitly deprioritized (§K). **Prereq:** evidence fixture. |
| **E8.5 Hypothesis / Gap / Report views** *(Wk 13–14)* | Ranked causes with supporting *and contradicting* evidence; gap view; report with clickable evidence refs. **Every conclusion reachable from its evidence in ≤2 interactions.** Confidence shown adjacent to each claim. **Prereq:** hypothesis + report fixtures. |
| **E8.6 Swap mock → real** *(Wk 15–16)* | Point at the live API endpoint by endpoint. **Because both sides were built against the same contract, this should be a config change, not a rewrite.** Then System Health + Analytics screens. **Prereq:** E7 complete. |

## E9 · Evaluation & Hardening — Weeks 17–18
> **GATE 7 — benchmark results and failure modes are measurable.** *Week 17 doubles as slack.*

| | |
|---|---|
| **E9.1 Golden benchmark run** | **Finally open the 2 held-out cases.** Full pipeline, all metrics, baseline-vs-advanced comparison table for every learned component. **Result:** `artifacts/benchmark-reports/final.md`. |
| **E9.2 Failure analysis & model cards** | Catalogue every failure mode with a frame screenshot and a root cause. Model card per promoted model (purpose, data, metrics, **limitations**, version). Honest limitations sections are what distinguish this from a demo. |
| **E9.3 Performance profiling** | End-to-end latency, FPS, peak VRAM, queue depth. **Only now** consider parallelizing streams — and only where the profile shows benefit (spec §11). |
| **E9.4 Test suite completion** | Fill spec §L: unit (geometry, timestamps, evidence states) · integration (ingest→observation→event→incident) · API (schemas, errors, idempotency) · e2e (golden case → expected timeline) · Playwright (replay sync, evidence navigation) · **failure tests: worker restart, corrupt video, Redis down, one camera missing**. |

## E10 · Productionization — Week 19
> **GATE 6 — a new developer can run the system from the repository.**

| | |
|---|---|
| **E10.1 Full Compose stack** | api + worker + postgres + redis + web in one `docker-compose up`. **Verification: clone to a fresh directory and follow only the README.** If you touch anything not in the README, the README is wrong. |
| **E10.2 Observability** | Structured logs (structlog); `/health` and `/metrics`; the spec §N metric set: queue depth/age, FPS, VRAM, ID-switch rate, event rate, report latency, API latency/errors, retries/dead-letters, evidence coverage, unsupported-claim rate. |
| **E10.3 Security & privacy pass** | Basic auth + one role boundary; raw-video access separated from derived metadata; evidence access logged; retention/deletion rules documented; responsible-use statement (spec §M) in the README **and** in every generated report. |
| **E10.4 ADR: why not Kafka** | Write the distributed-systems decision up properly — context, options, decision, consequences, and the concrete trigger that would justify revisiting. This is a deliverable, not an excuse. |

## E11 · Delivery — Week 20
Demo video (end-to-end, showing an UNKNOWN interval prominently) · technical presentation · final
academic report · future-work roadmap · repository final pass.

### Stretch backlog — attempt only if Week 19 finishes early, in this order
1. **Public-footage realism check** (WILDTRACK / MMPTRACK) — highest evidential value; proves the
   pipeline isn't overfit to synthetic data.
2. **LLM report layer** — local quantized model via Ollama, strictly after the evidence graph,
   consuming structured evidence only, deterministic template retained as fallback. Add an
   unsupported-claim regression test comparing LLM output against template output.
3. **Kafka/Redpanda split** — perception moved behind an event bus.
4. AWS deployment demo · OpenTelemetry traces.

---

# PART 3 — POST PHASE (continuous + Week 20 close-out)

Runs *alongside* execution, not after it. Two cadences.

## 3.1 Weekly drift check — 30 minutes, every Friday

Write the weekly log (spec §O4) and answer four questions:

1. **Did the plan hold?** Which sub-phases completed vs planned.
2. **What deviated?** Every deviation gets a row in `docs/deviation-ledger.md`:

   | Field | Meaning |
   |---|---|
   | Date / sub-phase | Where it happened |
   | Planned | What this document said |
   | Actual | What you did |
   | **Classification** | **IMPROVEMENT** (better than planned — amend this roadmap) · **NEUTRAL** (equivalent path) · **DEBT** (worse; needs paying back) · **SCOPE-CREEP** (outside the charter) |
   | Cost | Days gained/lost |
   | Action | Amend plan / repay by date / revert / accept |

   **The classification is the point.** Deviation is normal; unclassified deviation is how a project
   silently becomes something else. A row marked SCOPE-CREEP goes straight to the post-MVP backlog.
3. **Did any benchmark metric regress?** If a number moved, an experiment record must explain it.
   A silent regression is the failure mode this whole system exists to prevent.
4. **Which risk moved?** Update the register. Any risk that hit its escalation trigger gets addressed
   next week, not "soon".

## 3.2 Gate reviews — 7 hard checkpoints

At each gate, before proceeding:

| Check | Question |
|---|---|
| Exit criteria | Are the gate's stated criteria *measurably* met, with numbers in the benchmark report? |
| Contract integrity | Did the implementation match the frozen PS-4 schema, or did the schema drift silently? Diff `openapi.json` and the Pydantic models against their Week-1 versions. |
| Fixture parity | Does the real output still validate against the golden fixture shape? If not — bug or intentional contract change? An intentional change requires a `schema_version` bump and an ADR. |
| Test coverage | Does critical logic in this phase have automated tests, or did tests get deferred? Deferred tests are DEBT rows. |
| Documentation | ADRs for decisions made, experiment records for models trained, CHANGELOG for user-visible behaviour. |
| Charter alignment | Does the phase still serve the DoD, or did it grow features nobody asked for? |
| Honest verdict | **Is this gate genuinely passed, or am I passing it because it's on the calendar?** Write the answer down. |

**A failed gate is a valid outcome.** Record it, decide explicitly: fix, descope, or accept and
document the limitation. Do not proceed while pretending.

## 3.3 Final audit — Week 20

- **DoD walkthrough** — all 15 lines of spec §P, each marked met / partially met / not met with evidence.
- **Deviation ledger review** — sum the DEBT rows. Anything unpaid goes in the final report's
  limitations section. *Every IMPROVEMENT row is material for the report* — it shows engineering
  judgement under real constraints, which is more interesting than a plan that was followed perfectly.
- **Spec-vs-built diff** — a table of what the original `.docx` promised vs what exists, with a
  one-line reason for each gap. Written by you, not discovered by a reviewer.
- **Reproducibility test** — hand the repo to someone else. Can they render the dataset, run the
  pipeline, and reproduce your benchmark numbers from the README alone?
- **Postmortem** (spec §O5 template) on the single biggest thing that went wrong.

---

# PART 4 — TOOLING

Choose from these. **Necessary** = the plan assumes it; removing it requires a replacement.
**Optional** = real value, real cost; skip without breaking the plan.

## 4.1 Necessary

| Area | Tool | Why this one |
|---|---|---|
| Language | Python 3.12 | Spec §C. |
| Package mgr | **uv** | Fast, lockfile, spec §I already lists `uv.lock`. |
| Deep learning | PyTorch + CUDA (version pinned in PS-2) | Spec §C. |
| Detector | Ultralytics YOLO (v8/v11 compact) | Spec §C. **Note: AGPL-3.0 — fine for academic work, flag it in the charter.** |
| Tracker | ByteTrack (bundled with Ultralytics) | Spec §C, no extra dependency. |
| CV utils | OpenCV + ffmpeg | Decode, sample, draw. |
| **CV glue** | **`supervision`** (Roboflow, MIT) | Zone polygons, line crossings, annotators, detection format conversion. Replaces ~500 lines you'd otherwise write. Highest-leverage single library here. |
| API | FastAPI + Uvicorn + Pydantic v2 | Spec §C; OpenAPI generation is what makes PS-4 work. |
| DB | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic | Spec §C; JSONB for evidence/config. |
| Cache/queue | Redis + **ARQ** | ARQ is async-native and pairs with FastAPI far more simply than Celery. |
| Dataset | **Blender** (+ Python API) | Free, scriptable, exact ground truth. |
| Frontend | React + TypeScript + Vite | Spec §C. |
| Styling | Tailwind CSS + **shadcn/ui** | Copy-in components, no runtime lock-in, tokens map to PS-8 cleanly. |
| Server state | TanStack Query | Caching/refetch for a polling investigation UI. |
| Graph viz | **React Flow** | Interactive node/edge with custom node components — needed for evidence-state styling. |
| Containers | Docker + Compose | Spec §C. |
| Testing | pytest, pytest-asyncio, httpx, **Playwright** | Spec §C/§L. |
| Metrics | `motmetrics` | IDF1 / ID-switch scoring without hand-rolling MOT metrics. |
| Lint/types | Ruff + mypy | One tool for lint+format; types make the frozen contracts real. |
| Logging | structlog | Structured logs from day one. |
| CI | GitHub Actions | Spec §C. |
| Docs | Markdown + Mermaid + ADRs | Spec §C/§O. |

## 4.2 Optional — worth the cost

| Area | Tool | Verdict |
|---|---|---|
| Experiment tracking | **MLflow** (local) or W&B | **Recommended.** Spec §O demands an experiment registry; markdown works but MLflow makes comparison tables automatic. MLflow keeps everything local. |
| Re-ID embeddings | `torchreid` / OSNet, or CLIP crop embeddings | **Recommended for E5.2** — but only *after* the cheap colour-histogram baseline is measured. |
| Dataset versioning | DVC or `git-lfs` | Useful if renders exceed a few GB. Manifest + checksums (E1.3) may be enough. |
| Vector search | pgvector | Only if you implement semantic evidence retrieval (spec §10). Postgres extension, low cost to add. |
| Load testing | Locust | Spec §L asks for it; one afternoon. |
| Charts | Recharts or visx | For System Health / Analytics screens. Custom canvas is better for the timeline itself. |
| Video playback | plain `<video>` + `requestVideoFrameCallback` | **Prefer this over video.js/hls.js** — you need frame-level sync control, and a player library fights you. |
| Client state | Zustand | Only if playback state gets genuinely awkward in React state. |
| Error tracking | Sentry (free tier) | Nice for the demo's System Health screen. |
| API mocking | MSW | Alternative to the PS-5 mock server if you'd rather mock in the browser. |

## 4.3 Optional — stretch only

| Tool | When |
|---|---|
| Redpanda (Kafka API, single binary) | Stretch #3. Far lighter than Kafka for local demo. |
| Local LLM: **Ollama** + Qwen2.5 7B / Llama 3.1 8B quantized | Stretch #2. Fits 6 GB at Q4. |
| `instructor` / structured outputs | With the LLM — forces schema-conformant, citable output. |
| Prometheus + Grafana | Stretch. Compose adds 2 services. |
| OpenTelemetry | Stretch. Only meaningful once services are actually split. |
| AWS (S3, ECS/Fargate, RDS) | Stretch. Watch cost; spec §K says local-first. |
| CVAT / Label Studio | Only if you add public footage (stretch #1) — simulated data needs no annotation. |
| Unity Perception / NVIDIA Omniverse Replicator / CARLA | Only if Blender proves inadequate. Document as an ADR before switching. |
| Neo4j | **Recommend against.** Postgres recursive CTEs handle this graph size; a second database is a real operational cost for no gain at this scale. |

## 4.4 Explicitly rejected (write these as ADRs — the reasoning is a deliverable)

Kafka/microservices at MVP · Neo4j · training a detector from scratch · face recognition (spec §M) ·
Kubernetes · a component library heavier than shadcn · cloud-first deployment.

---

# PART 5 — DESIGN RESOURCES

## 5.1 Direct references — closest to what you're building

Study these *first*; they're the same problem domain and will teach you more than general galleries.

| Source | What to take from it |
|---|---|
| **play.grafana.org** | Live public Grafana. The reference for dark operational dashboards, dense data, time-range pickers. |
| **Sentry** / **Linear** / **Vercel** dashboards | Dark UI done with restraint; excellent status/severity encoding; Linear's information density is the bar. |
| **Voxel51 FiftyOne** | Open-source CV dataset explorer — video + detections + timeline in one view. Closest existing tool to your Incident Workspace. Run it locally. |
| **Frame.io** / **Descript** | Multi-track video timeline interaction, scrubbing, and clip navigation done properly. |
| **Roboflow** / **Scale Nucleus** | Annotation and evidence-review interaction patterns. |
| **Milestone XProtect** / **Genetec** / **Verkada** / **Rhombus** (product tours) | Actual VMS investigator UIs — multi-pane synchronized playback. Also useful as a *contrast*: they show video, you show reasoning. |
| **Neo4j Bloom** / **Obsidian graph view** | Node-link layouts that stay readable at 50–200 nodes. |
| **Datadog Watchdog / Incident Management** | Root-cause presentation with confidence and supporting signals — directly analogous to your Hypothesis Panel. |

## 5.2 General UI inspiration

**Mobbin** (best-in-class, real product flows) · **Dribbble** · **Behance** · **Awwwards** ·
**Land-book** · **SaaSFrame** · **Godly** · **Refero** · **Page Flows** (recorded user flows) ·
**Nicelydone** · **Screensdesign** · **UI Sources** · **Tailwind UI** (dashboard patterns) ·
**Untitled UI** · **Tremor blocks** (dashboard components).

## 5.3 Colour

| Tool | Use |
|---|---|
| **Radix Colors** | **Start here.** Purpose-built accessible scales with automatic dark-mode pairs — exactly right for an evidence-state palette needing guaranteed contrast. |
| **Realtime Colors** | Preview a full palette on a real UI mockup instantly. |
| **Huemint** | ML palette generation constrained by role (background/surface/accent). |
| **Adobe Color** | Colour-wheel harmonies + **colourblind-safe checker**. |
| **Coolors** | Fast iteration, exports to CSS/Tailwind. |
| **Leonardo** (Adobe) | Generates palettes from *target contrast ratios* rather than hues — best fit for your accessibility requirement. |
| **Open Color** | Well-tuned open-source scales. |
| **Happy Hues** | Palettes shown in context, with usage guidance. |
| **Tailwind palette** | Sane default if you'd rather not design a palette at all. |

**Contrast & colourblind verification (non-negotiable per PS-8):** WebAIM Contrast Checker ·
**Who Can Use** · Coblis colourblind simulator · APCA contrast calculator · Chrome DevTools vision
deficiency emulation.

## 5.4 Typography

**Google Fonts** · **Fontshare** (free commercial-grade) · **Typewolf** (pairings in the wild) ·
**Fontpair** · **Modern Font Stacks** (zero-download system stacks).

*Suggestion for this project:* **Inter** or **Geist** for UI, and a genuine monospace — **JetBrains
Mono** or **IBM Plex Mono** — for timestamps, IDs and evidence refs. Tabular numerals matter when
timestamps stack vertically in a timeline; without them the columns visibly jitter.

## 5.5 Icons & imagery

**Lucide** (matches shadcn/ui) · **Phosphor** · **Tabler** · **Heroicons** · **Radix Icons** ·
**Iconify** (search across all sets).

Images: **Unsplash** · **Pexels** · **Lummi** (AI-generated, free). Illustration for empty states:
**unDraw** · **Storyset** · **Open Peeps**.

## 5.6 Data visualisation reference

**Observable** · **D3 gallery** · **Nivo** · **visx** · **Datawrapper Academy** (chart-choice guidance)
· **FlowingData** · Edward Tufte's data-ink principle — directly applicable to a dense timeline where
every pixel of chrome competes with evidence.

## 5.7 Motion

**Framer Motion** examples · **Motion One** · **GSAP** showcase.

Keep motion minimal here: an investigator tool should feel *instant*, not animated. Reserve transitions
for state changes that need explanation — a timeline seek, a graph node expanding.

---

# PART 6 — VERIFICATION

## How to verify the pre-phase is genuinely done
```bash
git clone <repo> /tmp/verify && cd /tmp/verify
make dev            # env builds from lockfile
make test           # CI-equivalent passes
alembic upgrade head # schema applies to an empty DB
make mock           # mock API serves all 8 endpoints from golden fixtures
make bench          # emits a benchmark report (perfect scores against fixtures)
uv run scripts/bootstrap/smoke_gpu.py   # prints the measured VRAM table
```
Plus: open the PS-8 swatch page and confirm all five evidence states are distinguishable in
greyscale and under a deuteranopia simulation.

## How to verify each execution sub-phase
1. Its output validates against the frozen schema (`pydantic` parse of real output).
2. Its metrics appear in `artifacts/benchmark-reports/` — a sub-phase with no number isn't verified.
3. Its unit/integration tests pass in CI.
4. An experiment record exists for any model or threshold decision.

## How to verify the whole system (Gate 6, end to end)
```bash
docker compose up
# UI at localhost:5173
```
Then, entirely through the browser: create a case from the 3 golden videos → watch it process →
open the incident → scrub the synchronized replay → click a timeline event and confirm **all three
cameras seek to that timestamp** → open the evidence graph → click a node and confirm it navigates to
its source frame → open the report → click an evidence reference and confirm it resolves → confirm the
occluded interval is rendered as UNKNOWN and the report says "cannot determine" about it.

Automated equivalent: the Playwright e2e suite (E9.4) plus `tests/e2e/test_golden_case.py`, which
asserts the full pipeline reproduces the expected timeline for a held-out case.

---

# Appendix — Week-by-week at a glance

| Wk | Focus | Gate / Milestone |
|---|---|---|
| 0–1 | Pre-start: charter, env, repo, **contracts, fixtures**, scene design, eval stub, design tokens | Pre-start checklist |
| 2–3 | E1 Blender scene, render 6 cases, ground truth, manifest | M1 |
| 4 | E2 ingestion + run registry · *E8.1 UI shell begins on mock* | M2 |
| 5–7 | E3 detection, tracking, persistence · *E8.2 replay* | **Gate 1** |
| 8–9 | E4 geometry, semantic events, timeline · *E8.3 timeline UI* | **Gate 2** |
| 10–11 | E5 sync, appearance, cross-camera association · *E8.4 graph UI* | **Gate 3** |
| 12 | E6 incident triggers + rewind orchestration | M6 |
| 13–14 | E7 evidence graph, hypotheses, uncertainty, report · *E8.5 report UI* | **Gates 4 & 5** |
| 15–16 | E8.6 UI wired to real API, health + analytics screens | M8 |
| 17 | E9 golden benchmark, failure analysis · **slack** | **Gate 7** |
| 18 | E9 profiling + full test suite | |
| 19 | E10 Compose, observability, security, ADRs | **Gate 6** |
| 20 | E11 demo, presentation, report · **slack / stretch** | Final audit |

**Load-bearing weeks: 13–14 (E7).** If the schedule slips, cut UI polish, cut learned components, cut
the second incident class — protect the evidence graph and the deterministic report. They are the
project's argument.

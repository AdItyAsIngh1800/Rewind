# Week 0 — 2026-09-09

Pre-start phase. Nothing in the execution phase begins until the checklist below is
complete.

## Objectives set

Complete PS-1 through PS-9 from `ROADMAP.md`.

## Completed

| Sub-phase | Status | Evidence |
|---|---|---|
| PS-1 Scope freeze & charter | **Done** | `docs/00-project-charter.md` — 2 incident classes, 3 cameras, 6 cases, 4 entity classes frozen; DoD transcribed with provisional benchmark floors |
| PS-2 Hardware & environment baseline | **Done** | `docs/09-deployment.md` §7 with measured numbers; `scripts/bootstrap/smoke_accel.py` |
| PS-3 Repo skeleton, docs system, CI | **Done** | 50 directories each with a scope README; CI green on `main` |
| PS-4 Contract freeze | **Done** | `packages/schemas/`, `openapi.json` (9 paths), `alembic upgrade head` builds 11 tables |
| PS-5 Golden fixtures + mock API | **Not started** | — |
| PS-6 Scene & incident design | **Done** | `docs/dataset/scene-spec.md` — coordinates, zones, cameras, 6 case scripts |
| PS-7 Evaluation harness stub | **Not started** | — |
| PS-8 Design language | **Not started** | — |
| PS-9 Risk register & gate calendar | **Done** | `docs/risk-register.md` — 20 risks, 7 gates dated |

## Benchmark movement

First measurements exist. No baseline to compare against yet.

| Metric | Value | Note |
|---|---|---|
| Detection throughput, 720p batch 1 | 33.6 FPS | `yolo11n`, MPS, synthetic frames |
| Detection throughput, 720p batch 4 | 106.5 FPS | |
| Peak driver memory | 1.06 GB | against an 11.8 GB working-set ceiling |
| Test suite | 31 passing | 20 contract, 11 API |

## Failures and what they cost

- **CI red on first push.** Two `E501` line-length errors plus `pytest` exiting 5 on an
  empty suite. Cost ~10 minutes. The empty-suite failure was arguably correct behaviour
  — it went away when PS-4 brought real tests, which is the right order.
- **Port 5432 collision.** A Homebrew PostgreSQL 15 was already bound and won the
  localhost race, surfacing as `role "rewind" does not exist` rather than a port
  conflict. Cost ~10 minutes of misdiagnosis. Resolved by moving the project container
  to 5433 rather than touching the existing service.
- **`uv` selected Python 3.13 locally while CI installed 3.12.** Caught by a
  deprecation warning naming the interpreter path. Pinned via `.python-version`.

## Decisions made

- `ADR-0001` — modular monolith over microservices.
- `ADR-0002` — AGPL-3.0, keep Ultralytics, private repo until delivery.
- Hardware retargeted from RTX 4050 / CUDA to Apple M4 / MPS (`docs/09-deployment.md`).

## Deviations logged

Six rows in `docs/deviation-ledger.md`. The consequential ones:

- Hardware retarget — `NEUTRAL`.
- 32 GB free disk against a spec assuming 200 GB — `DEBT`, partly repaid by never
  persisting Blender passes.
- Frame sampling re-justified from GPU-load control to reproducibility — `IMPROVEMENT`.

## Risks that moved

- **R1 unified-memory pressure: High → Low.** Measured 1.06 GB peak against 11.8 GB.
- **R17 hardware mismatch: Open → Resolved.**
- **R19 disk headroom: new, High.** Escalates below 15 GB free.
- **R20 no Metal passthrough in Docker: new.** The worker runs on the host in
  development; the container image is CPU-only. Gate 6 criteria amended accordingly.

## The thing worth noticing

The machine is roughly **ten times faster than the dataset requires**. Most of the
specification's hardware-conscious guidance — sample frames to control GPU load, run
streams sequentially, avoid reprocessing — was written for a memory-constrained CUDA
laptop and does not bind here. Detection over the entire 8,100-frame dataset takes
around 80 seconds.

That does not mean those practices get dropped. Deterministic sampling stays, but its
justification changed from *GPU budget* to *reproducibility*, and that reason is
unaffected by having a fast machine. The risk now is assuming the rest of the pipeline
is equally cheap. Cross-camera association, evidence graph construction and three
synchronized video streams in a browser are untested and are the likely real
bottlenecks.

## Next week

PS-5 golden fixtures and mock API, PS-7 evaluation harness, PS-8 design language. Then
the pre-start checklist closes and E1 begins.

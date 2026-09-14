# EXP-0012: Pipeline profile — where the time goes, and whether to parallelise

- **Date:** 2026-09-14
- **Status:** Complete

| Field | Value |
|---|---|
| Question | Spec §11 and the roadmap allow parallelising camera streams only where a profile shows benefit. Where does a run spend its time, at what throughput, and with what memory? |
| Method | `scripts/evaluation/profile_run.py`: `process_run` exactly as the worker calls it, per case, against an ephemeral Postgres, rolled back. Stage timers on `PipelineResult.stages_s` (added for this record; the worker logs them on every run). API latency by `curl` against the dev database's C01; queued-to-complete from stored `started_at` / `finished_at` of the product-path runs |
| Hardware | Apple M4, 16 GB unified memory, MPS; `yolo11n-rewind-v1`, batch 8 |
| Cases | all six, 3 × 450 frames each at 10 FPS (45 s of footage per case) |
| Report | `artifacts/benchmark-reports/profile-2026-09-14T171531Z.md` |

## Results

| Stage | Seconds per case | Share |
|---|---|---|
| Perception (decode, detect, track, describe), three cameras | 8.0–10.1 | **95 %** |
| Persist observations and segments | 0.24–0.45 | 4 % |
| Events, identity, incidents, graph, ranking, report | 0.02–0.05 | < 1 % |
| **Total** | **8.4–10.7** | |

- Throughput **160–170 FPS** through perception (133 on the first case, which pays the
  MPS warm-up); 45 s of three-camera footage in about 8.5 s, **5× real time**.
- Detector load 0.5 s, once per worker process.
- Peak RSS 690 MB; accelerator memory 1.1 GB, flat across cases.
- Product path (worker, queued → complete, stored on the run): 8.4–10.6 s per case,
  the same as in-process; the queue adds nothing measurable.
- API, warm, dev database: every endpoint under 20 ms (`/health` 0.5 ms, case, timeline,
  evidence, report, replay 4–9 ms, `/metrics` 9–16 ms because it reads Redis).

## Decision: no parallelisation

Perception is the whole cost, and it runs on one accelerator. Three camera threads would
share the same MPS device and the same detector; they cannot add throughput, only
contention and a non-deterministic frame order into the tracker, which the ingestion
module exists to prevent. Everything after perception is under half a second and not
worth a thread. The system runs 5× faster than its data arrives, on a laptop; spec §11's
sequential-in-process design stands, and the roadmap's condition for parallelising is
not met.

What would change this: more cameras than one accelerator can serve in real time, at
which point the split is by *camera set across worker processes*, not by thread, and
the queue already supports that (one job per run; a run per camera set would be an
E2.2 change).

## Metrics still `null`

`/metrics` reports `frames_per_second` as `null`. The run now measures it, but storing
it would add a field to `ProcessingRun`, a frozen contract. Left for E10.2 with the
other observability fields, in one `SCHEMA_VERSION` bump.

# 09 — Deployment and Hardware Envelope

- **Decided:** PS-2, 2026-09-09
- **Supersedes:** the master specification §H, which planned for an RTX 4050 laptop

---

## 1. The hardware changed

The specification's hardware section is written for an **RTX 4050 laptop, 6 GB VRAM,
CUDA, mixed precision**. The actual build machine is an **Apple M4, 16 GB unified
memory, arm64**. This is not a small difference, and pretending otherwise would have
produced a plan that failed in Week 5.

| | Spec assumed | Actual |
|---|---|---|
| Accelerator | NVIDIA RTX 4050, CUDA | Apple M4, Metal / MPS |
| Memory model | 6 GB dedicated VRAM, separate from system RAM | **16 GB unified** — model, frames and OS compete for the same pool |
| Precision | CUDA mixed precision (AMP) | MPS float32; float16 support is partial |
| Disk assumption | ≥ 200 GB free | **32 GB free** |

Recorded as a `NEUTRAL` deviation in the ledger — the plan changed because the world
did, not because the plan was wrong.

## 2. What unified memory changes

The spec's central hardware constraint was a hard 6 GB VRAM wall. That wall does not
exist here; a different one does.

- **There is no separate VRAM budget.** A 16 GB pool is shared by macOS, the browser
  running the investigator UI, Docker (Postgres + Redis), the Python process and the
  model. The realistic working budget for inference is **8–10 GB**, not 16.
- **The failure mode is different.** CUDA gives a clean out-of-memory error. Metal
  degrades by paging to disk, which looks like a mysterious 20x slowdown rather than a
  crash. **A sudden throughput collapse should be read as memory pressure first.**
- **`torch.mps.recommended_max_memory()`** is the number to watch, not a VRAM figure.

**Consequence for the plan:** the concurrency rule from the spec still holds and matters
*more* — one heavy workload at a time. Do not run a benchmark while Docker and the Vite
dev server are up. Benchmarks that ignore this will not be reproducible.

## 3. Operating envelope

| Resource | Envelope | Note |
|---|---|---|
| Video | 720p, 10 FPS | Unchanged from the spec — set by the scene spec, not the hardware |
| Detector | Compact YOLO (`yolo11n` / `yolo11s`) | Start at nano; move up only if recall floors are missed |
| Batch size | Start at 1; raise only after the smoke test | Measured, never assumed |
| Precision | float32 | MPS float16 coverage is uneven; revisit only if throughput binds |
| Concurrency | One heavy GPU workload at a time | Stop Docker and Vite before benchmarking |
| Streams | Sequential during development | Parallelise only where the E9.3 profile shows benefit |

## 4. MPS-specific hazards

These are known before they bite, which is the whole point of PS-2.

1. **Operator gaps.** Some ops have no MPS kernel and raise rather than fall back. Set
   `PYTORCH_ENABLE_MPS_FALLBACK=1` so they route to CPU instead of crashing — but treat
   every fallback as a performance bug to investigate, not a fix.
2. **Non-determinism across devices.** MPS and CPU results differ in the last decimals.
   Benchmarks must record the device, and golden-benchmark comparisons must not be run
   across different devices.
3. **`device='mps'` must be passed explicitly** to Ultralytics. It does not default to
   Metal the way it defaults to CUDA.
4. **Memory is not released eagerly.** Call `torch.mps.empty_cache()` between benchmark
   configurations or the second measurement inherits the first one's footprint.

## 5. Disk budget — the newly binding constraint

**32 GB free against a spec that assumed 200 GB.** This is now a live risk (R19).

| Consumer | Estimate |
|---|---|
| Python environment (torch, ultralytics, opencv) | ~4 GB |
| Docker images and volumes (Postgres, Redis) | ~4 GB |
| Rendered dataset — video only | ~0.5 GB |
| Model weights and caches | ~1 GB |
| `node_modules` for the web app | ~0.5 GB |
| **Total** | **~10 GB** |

That fits, but only because of one decision: **Blender's object-index and depth passes
are consumed in-process during rendering and never written to disk.** Persisting them
as per-frame image files would have cost roughly 10 GB on its own for 8,100 frames.
Ground truth is emitted as JSON directly. See the scene spec §7.

**Escalation trigger:** free space below 15 GB. At that point, compact derived
observations and prune Docker build cache before continuing.

## 6. Environment

```bash
make dev     # uv sync --all-extras
```

PyTorch on macOS arm64 ships with MPS support in the default wheel — there is no
index URL to pin and no CUDA variant to choose. This is genuinely simpler than the
CUDA path the spec anticipated.

**Verify the envelope on any machine before trusting a benchmark from it:**

```bash
uv run python scripts/bootstrap/smoke_accel.py
```

It prints a markdown table of throughput and memory delta per batch size. Paste the
result into §7 below with the date.

## 7. Measured envelope

> Populated by the first run of `smoke_accel.py`. An empty table here means PS-2 is
> not actually finished, regardless of what the checklist says.

_(pending first run)_

## 8. Runtime topology

Unchanged by the hardware decision — see `ADR-0001`.

| Service | Container | Notes |
|---|---|---|
| `api` | FastAPI + Uvicorn | Metadata queries target sub-500 ms locally |
| `worker` | ARQ | Runs the perception pipeline off the request path. **Runs on the host during development**, not in Docker — containers cannot reach Metal |
| `postgres` | PostgreSQL 16 | Incident metadata, events, evidence |
| `redis` | Redis 7 | Job queue and transient investigation state |
| `web` | Vite dev server / static build | Investigator dashboard |

> **Docker cannot access the GPU on Apple silicon.** There is no Metal passthrough
> equivalent to `--gpus all`. The worker therefore runs on the host in development,
> and the containerized worker image is CPU-only — used for CI and for the Gate 6
> "clone and run" test, where correctness matters and speed does not. This is a real
> architectural consequence of the hardware decision and is called out in the Gate 6
> criteria rather than discovered during it.

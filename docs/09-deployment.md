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

Measured **2026-09-09**, `yolo11n.pt`, float32, MPS, `PYTORCH_ENABLE_MPS_FALLBACK=1`.
Five repetitions per configuration, synthetic 720p frames.

| Host | |
|---|---|
| Platform | Darwin 25.6.0 (arm64) |
| Chip | Apple M4, 10 cores |
| Unified memory | 16 GB |
| `torch` | 2.14.0 |
| `ultralytics` | 8.4.144 |
| **MPS recommended max working set** | **11.8 GB** |

| Resolution | Batch | ms/frame | FPS | Driver peak (GB) |
|---|---|---|---|---|
| 1280x720 | 1 | 29.7 | 33.6 | 0.06 |
| 1280x720 | 2 | 15.1 | 66.4 | 0.09 |
| 1280x720 | 4 | 9.4 | 106.5 | 1.06 |
| 1280x720 | 8 | 6.5 | 153.2 | 1.06 |

### What this actually means

**Detection is not the bottleneck, and was never going to be on this machine.**

- The dataset runs at **10 FPS**. Batch 1 alone delivers 33.6 FPS — a **3.4x margin**
  before any batching. At batch 4 it is more than 10x.
- Running the detector over the **entire 8,100-frame dataset takes roughly 80 seconds**
  at batch 4. The specification's hardware-conscious guidance — sample frames to control
  GPU load, run streams sequentially, avoid reprocessing video — was written for a 6 GB
  CUDA laptop and is largely moot here.
- Peak driver allocation is **1.06 GB against an 11.8 GB ceiling**: under 10% utilised.
  Risk R1 (memory pressure) is downgraded from High to Low likelihood.

**Three consequences for the plan.**

1. **Deterministic frame sampling stays** — but its justification changes. It is now
   about *reproducibility*, not GPU budget. Same input must always yield the same
   frames so a run can be replayed. That reason is unaffected by having a fast machine.
2. **A larger detector is affordable.** If the Gate 1 recall floor (≥ 0.90) is missed
   with `yolo11n`, moving to `yolo11s` or `yolo11m` costs throughput we demonstrably
   have. Do not do this pre-emptively — measure `yolo11n` on real rendered frames
   first, as an experiment record.
3. **Expect the bottleneck elsewhere.** Cross-camera identity association, evidence
   graph construction and the browser rendering three synchronized video streams are
   now the likely constraints. E9.3 profiling should look there first.

### Measurement caveats

- **Run-to-run variance is roughly 15–20%** at batch 1 (33.6 and 40.4 FPS on two
  consecutive runs). Thermal state and background load dominate at this speed. Any
  benchmark that matters must be repeated, and the median reported.
- Frames here are **synthetic noise**, which yields near-zero detections and therefore
  understates NMS cost. Real rendered frames with 3–6 entities will be slower. Re-run
  this against `C01` once E1.2 has produced actual video, and replace this table.
- These numbers are **MPS-specific**. The CI runner is CPU-only x86. Golden-benchmark
  comparisons must never be made across devices.

## 8. Runtime topology

Unchanged by the hardware decision — see `ADR-0001`.

| Service | Where it runs | Notes |
|---|---|---|
| `api` | Host (dev) / container | FastAPI + Uvicorn. Metadata queries target sub-500 ms |
| `worker` | **Host only in development** | ARQ. Cannot run in Docker in dev — no Metal passthrough |
| Database | **Supabase (hosted)** | Postgres 17 + Storage + Auth + RLS + pgvector. See `ADR-0003` |
| `redis` | Container | Job queue and transient investigation state |
| `web` | Vite dev server / static build | Investigator dashboard |

### Security posture

RLS is **enabled and forced** on all 12 application tables with no policies attached,
which denies every request except the service role. Verified rather than assumed:
inserting a row as the service role and reading with the anon key returns `[]`.

```bash
make verify-security   # fails loudly if any table ships without RLS
```

The weekly keep-alive workflow repeats the outside-in half of that check using only
the anon key, so no privileged credential lives in CI.

### Consequence for Gate 6

Gate 6 is "a new developer can run the system from the repository". With a hosted
database that becomes "…from the repository, **plus a Supabase project and its
credentials**". This is a genuine weakening and is recorded here rather than
discovered in Week 19. The README documents exactly which four values are needed and
where to find them; the Gate 6 check is that someone can go from clone to running
timeline using only that section.

> **Docker cannot access the GPU on Apple silicon.** There is no Metal passthrough
> equivalent to `--gpus all`. The worker therefore runs on the host in development,
> and the containerized worker image is CPU-only — used for CI and for the Gate 6
> "clone and run" test, where correctness matters and speed does not. This is a real
> architectural consequence of the hardware decision and is called out in the Gate 6
> criteria rather than discovered during it.

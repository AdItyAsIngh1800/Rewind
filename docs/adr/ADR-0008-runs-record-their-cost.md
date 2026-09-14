# ADR-0008: Processing runs record what they cost

- **Status:** Accepted
- **Date:** 2026-09-15
- **Amends:** the `ProcessingRun` contract (`SCHEMA_VERSION` 1.1.0 → 1.2.0), as `ADR-0006` did

## Context

Specification §N asks the system to report frame throughput and accelerator memory.
Since E9.3 every run measures its own stage timings (`PipelineResult.stages_s`), and
the worker logs them, but nothing stores them: `/metrics` has reported
`frames_per_second` as `null`, and a throughput figure measured once lived only in an
experiment record (EXP-0012) and in a log line.

Two places could hold it. A value the worker writes to Redis beside ARQ's health line
needs no contract change, but it is one number, overwritten by the next run, lost when
Redis restarts, and not attached to the run it describes. The project's discipline is
that a result traces back to exactly what produced it: the run carries its input hash,
dataset, model and config versions for that reason.

## Decision

**`ProcessingRun` gains three additive fields**, written by the pipeline when a run
completes:

| Field | Meaning |
|---|---|
| `frames_processed` | Frames decoded and passed through perception, across cameras |
| `stages_s` | Wall-clock seconds per stage: `perception:<camera>`, `persist:observations`, `events`, `identity`, `reasoning` |
| `peak_memory_mb` | Peak process resident memory plus the accelerator driver's allocation (MPS or CUDA), MB, at run end |

`/metrics` derives `frames_per_second` (frames over perception seconds) and
`peak_memory_mb` (the maximum) from the most recent completed runs that recorded them.

**The tracking ID-switch rate stays `null`**, with the reason in its description. An ID
switch is a track changing which true entity it follows, and production footage has no
ground truth to tell. System Health shows the held-out benchmark's measured value,
labelled as offline. A live proxy (tracks per linked identity) was rejected: it would
render under the name of a metric it does not measure, mixing identity errors into a
tracker number.

## Consequences

- `SCHEMA_VERSION` 1.2.0; migration adds three nullable or defaulted columns, so existing
  runs read as "not recorded", never as zero. Golden fixtures regenerated;
  `openapi.json` regenerated; the web and mock API types follow.
- A failed run records nothing: it has no complete stage set to be honest about.
- Memory is a process-level figure. The worker handles one run at a time, so the peak
  belongs to that run; a worker that processed runs concurrently would need a per-run
  measurement.

## Related

`ADR-0006` · EXP-0012 · specification §N · `services/observability/resources.py`.

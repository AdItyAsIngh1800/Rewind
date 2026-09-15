# ADR-0010: Why not Kafka — the database is the event log at this scale

- **Status:** Accepted
- **Date:** 2026-09-15
- **Confirms:** `ADR-0001` (written in week 0 on predictions; this record is written in
  week 19 on measurements)

## Context

The specification describes an event-driven system: perception services publishing
observations and semantic events onto Kafka, consumers building the timeline, the
evidence graph and the incident detector from the stream. `ADR-0001` chose a modular
monolith instead and named three triggers for revisiting. The roadmap (E10.4) asks for
that decision to be written up properly once the system exists, with the concrete
condition that would justify an event bus. This is that record.

What the built system actually does with events:

- **A run is the unit of work.** `POST /cases` records a run and enqueues one ARQ job
  on Redis. The worker runs perception, persistence, events, identity, incidents, the
  graph, ranking and the report in one process, in order, committing after each
  stage. Jobs are idempotent: a redelivered job returns the stored run's
  status (E2.2, `apps/worker/tasks.py`), and a run found `RUNNING` by a restarted
  worker is failed with a reason rather than silently re-run (E9.4).
- **Postgres is the store of record and the only thing downstream stages read.** Every
  stage after perception reads the previous stage's rows, never its in-memory output
  (spec §11). The tables are the event log: `observations`, `events`, `incidents`,
  keyed by run and indexed by time.
- **The internal event envelope from PS-4** (`packages/schemas/envelope.py`:
  `event_id`, `schema_version`, `event_type`, `event_time`, `producer_service`,
  `producer_version`, `evidence_refs`) exists as a contract and is on no wire. It was
  frozen so that a stage could be lifted onto a bus without changing its payload; no
  stage has needed lifting.

The measurements (EXP-0012, `artifacts/benchmark-reports/profile-2026-09-14T171531Z.md`):

| Quantity | Measured |
|---|---|
| Perception share of a run | 95 % (8–10 s of 8.4–10.7 s per case on MPS) |
| Everything after perception | under 0.5 s per case |
| Throughput on the laptop | 160–170 FPS, 5× real time; in Docker on CPU, 12–16 FPS |
| Rows per case | 1,400–2,500 observations, 5–26 events, 0–1 incidents |
| Queue overhead, queued → complete | not measurable against in-process |
| Cameras · cases | 3 · 6, prerecorded |

## Decision

**No event bus.** Redis remains the job queue, Postgres remains the event log, and
stages remain function calls in one worker process. Kafka (or Redpanda) is not added
at MVP and not scheduled; it stays stretch item 3 in the roadmap, unscheduled.

## What Kafka would buy, and why none of it is bought here

| Kafka property | What it would give REWIND | Why it is not needed at this scale |
|---|---|---|
| Durable, ordered, replayable log | Reprocess the stream from any offset | A run *is* replayable: it is a pure function of its input hash, dataset, config and model versions (E2.2). Reprocessing is `POST /cases` again. |
| Many consumers per stream | A live alerting consumer beside the reporting path | Every consumer today is a stage of the same run and reads Postgres. There is no second consumer. |
| Decoupled producers and consumers | Perception on GPU machines, reasoning elsewhere | Perception is 95 % of the cost and everything else is under half a second; there is nothing worth decoupling from it. |
| Backpressure and buffering under bursty ingestion | Absorb streams arriving faster than they are processed | Ingestion is prerecorded clips; the system runs 5× faster than its data on a laptop. Live RTSP ingestion is a charter non-goal. |
| Partitioning by key | Parallel perception per camera | EXP-0012: three camera threads share one accelerator and one detector, so they add contention, not throughput, and a non-deterministic frame order into the tracker. |
| Exactly-once / at-least-once semantics to reason about | — | Redis at-least-once plus an idempotent job already covers the failure tests (worker restart, Redis down, corrupt clip). |

## Alternatives considered

| Option | Why not |
|---|---|
| Kafka (KRaft) in compose | A broker to run, a schema registry to keep the frozen contracts honest on the wire, consumer groups and offsets to test, for a stream with one consumer. |
| Redpanda, single binary | Cheaper to run, same reasoning burden, same absent consumer. |
| Postgres `LISTEN/NOTIFY` as a bus | The tables already carry the state; a notification would only tell a consumer that does not exist to go and read them. |
| Redis Streams | Already present, so nearly free — and the same absent consumer. Would be the first step if a trigger below fires, before a broker. |

## Consequences

**Gained.** One process to debug, in-process tests that run the whole pipeline in
seconds, and no delivery semantics to reason about while the perception layer is
still the thing being tuned. Gate 6 is `docker compose up` with six services, none of
them a broker.

**Lost.** Perception cannot be scaled out without a change to how work is described:
today a job is a run; on a bus it would be a camera-clip. A long run occupies the one
worker. Neither has mattered at three cameras and six cases.

**Kept ready.** The envelope contract, the `producer_service` / `producer_version`
fields on every event, the hard `services/*` boundaries, and idempotent jobs. Lifting
perception onto a stream is a new producer and a new consumer around an unchanged
`process_run`; it is a deployment change with a test suite behind it, not a rewrite.

## The triggers, concretely

Revisit this decision — with Redis Streams first, a broker second — when any one of
these is **measured**, not predicted:

1. **A second consumer.** Something must react to events without waiting for the run's
   report: live alerting, a dashboard fed as frames arrive. The signal is a feature on
   the backlog that reads `events` before `reports` exists for the same run.
2. **Ingestion outpaces one worker.** `queue_oldest_age_s` on `/metrics` climbs across
   consecutive runs rather than returning to zero, at the throughput the deployment's
   hardware gives (12–16 FPS in a CPU container, 160+ on MPS). On the laptop that is
   roughly ten concurrent 10 FPS streams, `ADR-0001`'s first trigger.
3. **Perception must leave the worker's host.** A GPU machine for the detector with
   the API and database elsewhere. That needs a wire between them, and the wire should
   carry the envelope.
4. **Replay from the stream is needed and the run is no longer a pure function of its
   inputs** — a live source that cannot be re-read. This is the live-RTSP non-goal
   being lifted; it changes the charter before it changes the architecture.

Until one fires, this decision stands and is not re-litigated.

## Related

`ADR-0001` · EXP-0012 · `docs/00-project-charter.md` §4 · `apps/api/queue.py` ·
`apps/worker/tasks.py` · `packages/schemas/envelope.py` · roadmap E10.4, stretch 3 ·
specification §K "distributed-system complexity", §11.

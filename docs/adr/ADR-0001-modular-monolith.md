# ADR-0001: Modular monolith over microservices for the MVP

- **Status:** Accepted
- **Date:** 2026-09-09

## Context

The master specification describes an event-driven architecture with Kafka, split
perception services, S3-compatible object storage, OpenTelemetry and an optional AWS
deployment. It also, in its own challenge register, answers the entry
"distributed-system complexity" with *"modular monolith first; introduce Kafka and
service splits later."*

The project is a 20-week solo build on a fixed schedule. The risk budget was already
spent deliberately on the dataset decision (simulated rather than public footage) in
order to protect reproducibility and the schedule. The weeks that carry the project's
actual argument — cross-camera identity, evidence reasoning, and the investigator UI —
fall in weeks 10 to 16. Production infrastructure occupies a single week near the end
and is explicitly marked optional in the source timeline.

## Decision

Build REWIND as a **modular monolith**: one Python codebase with hard module
boundaries under `services/`, one FastAPI process, one ARQ worker process, Postgres and
Redis, all under Docker Compose. Services communicate through typed function calls and
the shared database, not a network hop.

The module boundaries are real and enforced: each `services/*` package owns its stage
of the pipeline and communicates only through the frozen contracts in
`packages/schemas/`. Splitting one out later is a deployment change, not a rewrite.

## Alternatives considered

| Option | Why not |
|---|---|
| Kafka + service split + AWS + OpenTelemetry from the start | Reintroduces exactly the schedule risk the simulated-dataset decision removed. Four new operational surfaces before a single frame has been detected. |
| Monolith, then a genuine event-bus split as a scheduled late phase | Strong résumé signal, but scheduling it means the last two weeks are committed to infrastructure rather than to evaluation and the demo. Kept as stretch item 3, unscheduled. |

## Consequences

**Easier.** One process to run and debug. No message-delivery semantics to reason about
while the perception pipeline is still wrong. Tests are in-process and fast. A new
developer runs `docker compose up` and gets everything.

**Harder.** Perception cannot be scaled independently of the API. A long inference job
occupies the worker. Neither matters at three cameras and six prerecorded cases.

**Expensive to reverse?** No — and this is the point of paying for hard module
boundaries now. The internal event envelope defined in PS-4 already carries
`event_id`, `schema_version`, `producer_service` and `producer_version`, so a stage can
be lifted onto a bus without changing its payload contract.

## Validation plan

Revisit if any of these become true:

- Sustained ingestion of more than roughly ten concurrent streams.
- Perception throughput becomes the binding constraint on end-to-end latency, proven
  by the E9.3 profile rather than assumed.
- A second consumer needs the event stream independently of the reporting path.

Until one of those triggers fires, this decision stands and is not re-litigated.

## Related

`ROADMAP.md` E10.4 · spec §K "distributed-system complexity" · spec §J weeks 6–7.

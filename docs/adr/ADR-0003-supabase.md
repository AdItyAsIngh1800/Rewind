# ADR-0003: Supabase as the database, object storage and auth layer

- **Status:** Accepted
- **Date:** 2026-09-09
- **Amends:** `ADR-0001` (runtime topology only — the modular monolith decision stands)

## Context

PS-4 froze the schema against a plain PostgreSQL 16 container. Three requirements from
the specification were still unimplemented and scheduled late:

- **Object storage** for video segments and evidence snapshots (§C, §E2), planned as
  "local filesystem, then S3-compatible later".
- **Role-based authorization and evidence access logging** (§M), scheduled for E10.3
  and to be hand-rolled.
- **Vector search** for semantic retrieval of evidence descriptions (§C), listed as
  optional.

Supabase is PostgreSQL with those three capabilities already attached. Adopting it does
not add scope; it implements scope that was already committed, earlier and with less
code.

## Decision

**Supabase replaces the PostgreSQL container** as the database for development and
delivery. Storage buckets hold media and evidence snapshots. Auth and Row Level
Security provide the §M role boundary. `pgvector` is enabled at the outset so E7
semantic retrieval needs no migration later.

**FastAPI, SQLAlchemy and the frozen `openapi.json` are unchanged.** PostgREST is not
used. The value of this system is in its reasoning endpoints — evidence graph, ranked
hypotheses, report — which are not CRUD, and an auto-generated CRUD API would buy
nothing while discarding the contract that the whole contract-first strategy depends
on.

### Schema authority

**Alembic is authoritative.** Schema flows one way:

```
frozen Pydantic contract -> SQLAlchemy model -> Alembic migration -> database
```

Supabase migrations under `supabase/migrations/` are used **only** for what Alembic
cannot express: extensions, Row Level Security policies, and storage buckets. They
never create or alter an application table.

**Supabase Studio is a debugging tool, not a schema editor.** If a change is ever made
through Studio, it must be reflected back into the SQLAlchemy model and captured in an
Alembic migration. An unreflected Studio change is schema drift, and detecting drift is
precisely what the contract chain exists to do.

### Connection strategy

Connections go through the **Supavisor session pooler**, not the direct database
endpoint.

Direct connections (`db.<ref>.supabase.co`) are IPv6-only for projects created after
early 2024 and fail outright on IPv4-only networks — a failure that presents as an
opaque timeout rather than a clear error. The pooler is dual-stack.

Session mode (port 5432) is used rather than transaction mode (6543) because session
mode supports prepared statements, which both Alembic DDL and SQLAlchemy's defaults
rely on. Transaction mode would require disabling prepared statements throughout for a
benefit — connection multiplexing at serverless scale — that a single API process and
a single worker do not need.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the plain Postgres container; build storage and auth by hand in E10.3 | Defers work already committed in the specification, and the hand-rolled version would be worse than the managed one. |
| Adopt PostgREST and Supabase Realtime, replacing much of FastAPI | Discards the frozen API contract that lets the frontend be built against a mock from Week 4. The reasoning endpoints are not CRUD. |
| Supabase migrations as the authority, dropping Alembic | Breaks the contract → model → schema chain established in PS-4, and makes drift from the Pydantic contracts undetectable. |
| Local Supabase stack for development | Rejected in favour of a hosted project, accepting the network dependency. Revisit if auto-pause proves disruptive. |

## Consequences

**Gained.** Object storage, an auth system, RLS and `pgvector` without writing any of
them. Managed backups. A cloud demo path that needs no AWS, which retires the cost
concern in specification §K.

**Lost — and this is the real cost.** Development now requires network access and
credentials. **Gate 6 is directly weakened**: "a new developer can run the system from
the repository" becomes "…from the repository, plus a Supabase project and its
secrets." The Gate 6 criteria are amended to state this explicitly rather than letting
it be discovered in Week 19.

**Free-tier constraints.** Two active projects per organisation, and projects pause
after roughly seven days of inactivity. A weekly GitHub Action pings the REST API to
keep the project awake; an un-pause from the dashboard takes about a minute if it
happens anyway.

**RLS is enabled deny-by-default now, with policies designed in E10.3.** Enabling RLS
with no policy denies all access except the service role, which is the correct safe
default and costs nothing today. Designing the full investigator/admin policy set
before there are any users would be speculative.

**Test isolation.** CI integration tests run against an ephemeral `postgres:16`
service container, not against Supabase. Tests that mutate a shared hosted database
are neither hermetic nor repeatable, and pointing CI at production to run them would
trade a real property — reproducible tests — for a cosmetic consistency. The secrets
in CI are used for the keep-alive ping only.

## Validation plan

- `alembic upgrade head` against Supabase produces the same 12 tables as the container.
- Contract and API tests pass unchanged — if any test needed editing, the swap leaked
  into application code and the abstraction is wrong.
- Storage buckets exist, are private, and evidence snapshots reject update and delete
  for non-service roles.
- Revisit if auto-pause interrupts work more than once, or if the free-tier database
  size limit is approached.

## Related

`ADR-0001` · `docs/09-deployment.md` · specification §C, §E2, §M.

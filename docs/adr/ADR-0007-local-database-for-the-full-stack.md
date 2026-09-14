# ADR-0007: A disposable local Postgres for the full stack

- **Status:** Accepted
- **Date:** 2026-09-15
- **Amends:** `ADR-0003` (scope of where Supabase is required; nothing else)

## Context

`ADR-0003` made Supabase the database for development and delivery, and recorded the
cost honestly: Gate 6, "a new developer can run the system from the repository",
became "…plus a Supabase project and its secrets" (ledger DEBT, risk R23).

Two things have happened since. CI already runs against an ephemeral
`pgvector/pgvector:pg16` container, on the principle that a check which must start from
nothing should not depend on a shared hosted database. And Gate 6 is that same kind of
check, run by a person: the roadmap's verification is clone, `docker compose up`, open
the UI. A step that requires creating a third-party account first is not part of that
script, and it is a step the project's own agent cannot verify, because reading the
Supabase credentials is deliberately blocked.

## Decision

**The full compose stack (E10.1) runs its own Postgres**: `pgvector/pgvector:pg16`, the
same image as CI, prepared by `packages/database/docker-init.sql` with the same extension
schema and `search_path` that `supabase/migrations` and CI apply. Migrations run as a
compose step before the API and worker start.

**Supabase remains the hosted target.** Every component reaches its database through
`DATABASE_URL` or the Supabase settings exactly as before; pointing the stack or a
development machine at Supabase is a configuration change, not a code change. Storage,
Auth and RLS policies in `supabase/migrations/` are unaffected.

## Alternatives considered

| Option | Why not |
|---|---|
| Compose against Supabase, as `ADR-0003` wrote | Gate 6 needs an account and secrets before anything starts; the fresh-clone check can only be run by the owner. |
| Local Supabase stack (`supabase start`) | Nine containers and the Supabase CLI to provide a Postgres the stack uses only as Postgres. |
| Plain `postgres:16` | Would pass on a schema the real database rejects: the `vector` extension set differs. The pgvector image is what CI already trusts. |

## Consequences

**Gained.** Gate 6 needs Docker, `uv`, and the GitHub CLI with access to the
repository for the data asset; no account, no secrets. The DEBT row from 2026-09-09
is repaid. Local, CI and full-stack databases are now the same image with the same
extension setup.

**Lost.** The full stack does not exercise the network path to Supabase (pooler
latency, auto-pause). `docs/09-deployment.md` §8 keeps the measured Supabase latencies,
and the keep-alive workflow still watches the hosted project.

**Data.** The compose database lives in a named volume, `pgdata`. `docker compose down -v`
discards it; nothing in it is not reproducible by reprocessing the cases.

## Related

`ADR-0003` · `docs/09-deployment.md` §8 · `docker-compose.yml` · roadmap E10.1, Part 6.

# REWIND

**Evidence-backed AI incident reconstruction engine for multi-camera video.**

After an abnormal event occurs, REWIND rewinds multiple camera streams, reconstructs
the timeline, connects evidence across views, ranks likely causes, and explicitly marks
uncertainty when the cameras cannot prove what happened.

The defining principle is **evidence before explanation**. The system distinguishes
confirmed observations from inferred relationships and unknown intervals. A claim can
never be phrased more confidently than its evidence permits, because the report
generator has no other vocabulary available.

---

## Status

Pre-start phase (Weeks 0–1). The pipeline does not run yet.

| | |
|---|---|
| Roadmap | [`ROADMAP.md`](ROADMAP.md) |
| Charter and scope freeze | [`docs/00-project-charter.md`](docs/00-project-charter.md) |
| Risk register and gate dates | [`docs/risk-register.md`](docs/risk-register.md) |
| Decisions | [`docs/adr/`](docs/adr/) |

## Quick start

cp .env.example .env   # then fill in the Supabase values below
make dev               # build the environment from the lockfile
make up                # start redis
make migrate           # apply database migrations to Supabase
make test              # run the suite
make help              # list every target
```

### Supabase setup

The database, object storage and auth are Supabase ([`ADR-0003`](docs/adr/ADR-0003-supabase.md)).
You need a project and four values in `.env`:

| Variable | Where to find it |
|---|---|
| `SUPABASE_PROJECT_REF` | The subdomain of your project URL, `https://<ref>.supabase.co` |
| `SUPABASE_DB_PASSWORD` | Set when the project was created; resettable in Settings → Database |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | Settings → API. **Server-side only — never sent to a browser** |

Then:

```bash
make db-url        # confirm the DSN resolves (password masked)
make migrate       # Alembic creates the application tables
make db-policies   # extensions, RLS and storage buckets
```

Connections go through the Supavisor **session pooler**, not the direct database
endpoint — the direct endpoint is IPv6-only and fails on IPv4-only networks with an
opaque timeout. `make db-url` shows what you are actually connecting to.

> **Schema authority:** Alembic owns the tables. Supabase Studio is for *reading* the
> evidence graph, not for altering it. A change made in Studio is schema drift — if it
> happens, reflect it back into the SQLAlchemy model and capture it in a migration.

The API contract is browsable without any of the above:

```bash
uv run uvicorn apps.api.main:app --reload
# http://localhost:8000/docs
```

Endpoints whose phase has not landed return **501**, not 404 — the shape is frozen,
the implementation is pending.

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12. `make dev` installs
everything else.

> **Gate 6** of this project is that a new developer can run the whole system from
> this README alone. If you have to touch anything not documented here, the README is
> wrong — that is a bug, please report it.

## Architecture in one paragraph

Three prerecorded camera streams are ingested and deterministically sampled. A compact
detector produces `Observation` records; a per-camera tracker groups them into
`TrackSegment`s; a cross-camera identity layer links segments **or explicitly refuses
to**. Trajectories become `SemanticEvent`s (zone entry, stop, proximity, occlusion). An
incident trigger opens an investigation window and rewinds it. An evidence graph is
built with provenance on every node and edge, candidate causes are ranked with both
supporting and contradicting references, and a deterministic generator writes a report
in which every material claim carries an evidence ID.

It is a **modular monolith**, containerized. It is deliberately not a microservice
system — see [`ADR-0001`](docs/adr/ADR-0001-modular-monolith.md).

## Responsible use

- Face recognition is **not** a feature of this system and will not be added.
- Only public, synthetic or explicitly permitted video is used. The MVP dataset is
  entirely simulated.
- REWIND is a decision-support tool. It must not be used as an autonomous
  disciplinary, legal or safety adjudicator.
- Every generated report states its own evidence limitations and uncertainty.

## Licence and attribution

REWIND is licensed **AGPL-3.0** — see [`LICENSE`](LICENSE).

This is inherited deliberately. Object detection and tracking use
[Ultralytics](https://github.com/ultralytics/ultralytics) (YOLO + ByteTrack), which is
AGPL-3.0, so this project adopts the same licence rather than pretending the obligation
away. The reasoning is recorded in
[`ADR-0002`](docs/adr/ADR-0002-licence-detector-hosting.md).

Practically: you may use, modify and self-host this freely. If you run a modified
version as a network service, you must offer your users its source.

## Repository layout

Every directory carries a `README.md` explaining what belongs in it. Start with
[`packages/schemas/`](packages/schemas/) — those contracts are frozen, and everything
else is written against them.

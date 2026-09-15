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

The pipeline runs end to end: three rendered camera feeds become an incident, an
evidence graph, ranked causes and a cited report, viewed in the investigator UI with
synchronized replay. Held-out results and every known failure are in
[`artifacts/benchmark-reports/final.md`](artifacts/benchmark-reports/final.md) and
[`docs/failures/`](docs/failures/README.md).

| | |
|---|---|
| Roadmap | [`ROADMAP.md`](ROADMAP.md) |
| Charter and scope freeze | [`docs/00-project-charter.md`](docs/00-project-charter.md) |
| Risk register and gate dates | [`docs/risk-register.md`](docs/risk-register.md) |
| Decisions | [`docs/adr/`](docs/adr/) |
| Architecture and data flow | [`docs/03-architecture.md`](docs/03-architecture.md) |
| ML design and experiments | [`docs/06-ml-design.md`](docs/06-ml-design.md), [`docs/experiments/`](docs/experiments/) |
| Evaluation plan and results | [`docs/07-evaluation-plan.md`](docs/07-evaluation-plan.md), [`artifacts/benchmark-reports/final.md`](artifacts/benchmark-reports/final.md) |
| Deployment and hardware, and running it on a server | [`docs/09-deployment.md`](docs/09-deployment.md) |
| Security, privacy, retention | [`docs/10-security-and-privacy.md`](docs/10-security-and-privacy.md) |
| Final report, audit, postmortem | [`docs/12-final-report.md`](docs/12-final-report.md), [`docs/audit/final-audit.md`](docs/audit/final-audit.md), [`docs/incidents/`](docs/incidents/) |
| Demo script, presentation, future work | [`docs/11-demo-script.md`](docs/11-demo-script.md), [`docs/13-presentation.md`](docs/13-presentation.md), [`docs/14-future-work.md`](docs/14-future-work.md) |
| Deviation ledger | [`docs/deviation-ledger.md`](docs/deviation-ledger.md) |

## Quick start — the whole system

Requires [Docker](https://docs.docker.com/get-docker/), [uv](https://docs.astral.sh/uv/)
and the [GitHub CLI](https://cli.github.com) signed in with access to this repository.

```bash
gh auth login          # once; the repository and its data asset are private
gh repo clone AdItyAsIngh1800/Rewind
cd Rewind
make fetch-data        # 42 MB, every file checked against data/manifests/v1.1.json
docker compose up --build
```

The first build takes a few minutes. When the log shows `worker` waiting for jobs, open
**http://localhost:5173** (set `REWIND_WEB_PORT` if that port is taken) and sign in on
the login page as `investigator` / `rewind`. The inbox is empty until a case is processed: click
**Process footage**, pick `case_01`, and queue the run. The same thing from a terminal:

```bash
curl -u investigator:rewind -X POST localhost:5173/api/v1/cases \
  -H 'Content-Type: application/json' \
  -d '{"dataset_version": "v1", "case_ref": "case_01"}'
```

The worker processes the three clips in about 90 seconds on CPU inside Docker (on Apple
silicon, `make worker` on the host uses MPS and takes about 10 seconds); the inbox
shows the run in progress and lists the incident when it completes. `case_01` to
`case_06` are available. `docker compose down -v` stops everything and discards the
database.

Everything runs locally: Postgres with pgvector, Redis, the API, the worker and the
UI ([`ADR-0007`](docs/adr/ADR-0007-local-database-for-the-full-stack.md)). No account
or secret is needed beyond the two demo sign-ins — `investigator` sees footage and
changes cases, `analyst` sees only the derived evidence — which `REWIND_USERS` in
`.env` replaces before anyone else can reach the UI
([`docs/10-security-and-privacy.md`](docs/10-security-and-privacy.md)).

## Development

```bash
make dev               # the environment from the lockfile, including the ML extra
make up                # redis
make migrate           # Alembic, against the database below
make api               # terminal 1
make worker            # terminal 2; on Apple silicon the detector uses MPS
make web               # terminal 3; the UI on http://localhost:5173
make test              # the suite; integration tests need DATABASE_URL
make help              # every target
```

The database is `DATABASE_URL` (any Postgres 16 with pgvector, prepared as in
[`packages/database/docker-init.sql`](packages/database/docker-init.sql)) or the hosted
Supabase project below.

### Hosted database: Supabase (optional)

Supabase is the hosted target for the database, object storage and auth
([`ADR-0003`](docs/adr/ADR-0003-supabase.md)). You need a project and four values in
`.env` (copy `.env.example`):

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

Every generated report repeats this in its limitations, so it travels with the report.
Who may see footage, what is logged when they do, and how long anything is kept:
[`docs/10-security-and-privacy.md`](docs/10-security-and-privacy.md).

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

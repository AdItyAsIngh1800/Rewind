# Changelog

User-visible and milestone behaviour only. Internal refactors do not appear here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-09-15

The MVP as delivered: `docs/12-final-report.md` for what it does and how well,
`docs/audit/final-audit.md` for the Definition of Done line by line.

### Added
- Pre-start: charter, frozen contracts (`SCHEMA_VERSION` 1.0.0), golden fixtures and
  a mock API, evaluation harness, design tokens, risk register and CI gate (PS-1–PS-9).
- Dataset `v1`: a Blender warehouse, three cameras, six scripted cases at 720p / 10 FPS
  with frame-exact ground truth; manifest with checksums; published as release
  `data-v1` and fetched by `make fetch-data` (E1).
- Ingestion and the run registry: deterministic sampling, per-camera clock offsets,
  runs identified by input hash and versions, idempotent jobs on Redis (E2).
- Perception: `yolo11n-rewind-v1` fine-tuned detector with a model card; ByteTrack per
  camera; observation store with a timestamp-range index (E3, Gate 1).
- Semantic events from trajectories and robot telemetry; `GET /cases/{id}/timeline`
  (E4, Gate 2).
- Cross-camera identity with explicit refusals, scored on false-link rate (E5, Gate 3).
- Two incident classes with automatic rewind windows (E6).
- Evidence graph with provenance, gap and conflict nodes; ranked hypotheses with
  support and contradiction refs; deterministic evidence-grounded report (E7, Gates 4–5).
- Investigator UI: case inbox, synchronized three-camera replay, timeline, evidence
  graph, hypothesis / gap / report views, System Health, Analytics; every selection
  seeks every camera (E8).
- Golden benchmark on the two held-out cases, failure catalogue with frames, pipeline
  profile, failure tests, golden end-to-end test, browser checks (E9, Gate 7).
- Full compose stack with a local Postgres (`ADR-0007`); JSON logs; `/metrics` with the
  spec §N set, run cost on each run (`SCHEMA_VERSION` 1.2.0) (E10.1–E10.2, Gate 6).
- HTTP Basic accounts with an analyst / investigator boundary on footage and changes;
  evidence access audit table and log event; retention rules and a deletion script;
  responsible-use statement on every report (E10.3, `ADR-0009`).
- `POST /cases/{id}/reprocess` under another config version.
- Runs record their footage and capture time (`SCHEMA_VERSION` 1.1.0, `ADR-0006`).

### Changed
- The database for the compose stack is a local `pgvector/pgvector:pg16`, not Supabase,
  which remains the hosted target (`ADR-0007`).
- Browser checks run on agent-browser rather than Playwright (ledger 2026-09-14).

### Known limitations
- On the held-out cases the detector misses a forklift colour absent from the tune
  data and a person at a fifth of their silhouette; cross-camera false-link rate 0.25
  against a floor of 0.05. `artifacts/benchmark-reports/final.md`, `docs/failures/`.
- Reprocessing selects a config version, not a model checkpoint.
- HTTP Basic needs TLS beyond localhost; there is no sign-out.

# Gate 6 — a new developer can run the system from the repository

- **Sub-phase:** E10.1
- **Date reviewed:** 2026-09-15 (calendar date: Tue 26 Jan 2027 — reached early)
- **Verdict:** **PASS**, verified the way the roadmap requires: a fresh clone from GitHub,
  following only the README. It failed on the first attempt, on two bugs a fresh clone
  was the only way to find; both are fixed and the check passed on a second fresh clone.

## Exit criteria

| Criterion | Evidence |
|---|---|
| Clone to a fresh directory and follow only the README | `gh repo clone` into an empty directory at `cf129dd`; `make fetch-data`; `docker compose up --build` (with `REWIND_WEB_PORT=5273`, the documented override, because 5173 was in use on the verifying machine) |
| The whole system starts from one command | `db`, `redis`, `migrate` (exits 0), `api` (healthy), `worker`, `web`: all up |
| A case is processed through the product path | `POST /api/v1/cases` for `case_01` through the UI's origin: 202, run `complete` in 87 s, one `robot_estop_human_incursion` incident in the inbox, report with 6 claims and its ranked cause |
| The investigator UI works on that stack | `make ui-check` against it (`REWIND_UI_URL`): **7 of 7** — panes open together, go-to-detection, frame step, play without drift, every report citation, a timeline event and a graph node each seek all three cameras. Footage streams through nginx with range requests (206) |
| No account, no secret | Database, queue, API, worker and UI are local (`ADR-0007`). The one external step is `gh auth login`, because the repository and its data asset are private |

## What the first attempt found

1. **The data asset carried 56 macOS AppleDouble entries.** Made with macOS `tar`, whose
   listing hides them. Extracted, `._CAM_A.mp4` sat beside `CAM_A.mp4`, the pipeline read
   it as a camera, and the run failed. The asset was rebuilt without macOS metadata and
   replaced under the same tag; every clip listing now goes through `case_clips`, which
   skips hidden files. The manifest check had passed: it verifies the files it lists,
   not extra ones.
2. **The two compose files shared the project name `rewind`** and both define `redis`, so
   starting the full stack on a machine running the dev file would have taken over its
   Redis. The dev file is now `rewind-dev`.

Also found: the image kept the uv download cache, 1.7 GB; removed (5.55 GB → 3.32 GB).

## Contract integrity

No contract changed. `SCHEMA_VERSION` `1.1.0`; `openapi.json` drift check green.

## Test coverage

317 passed against an ephemeral Postgres, including the `case_clips` test for hidden
files. The compose stack itself is verified by the procedure above, not by CI: CI has no
Docker-in-Docker and no rendered video. That is recorded, not hidden.

## Documentation

README quick start rewritten for the one-command stack; `ADR-0007`; deployment doc §8
topology; ledger rows for the database, the CPU worker, the data asset, the bugs, and a
correction to the worker's measured speed.

## Charter alignment

Nothing outside §4. Cloud deployment remains a non-goal; the stack is local by design.

## Honest verdict

Gate 6 is passed on its own terms: a stranger with repository access clones, fetches,
runs one command and investigates an incident, and the UI checks pass on what they get.
Two things are weaker than they sound. The worker in Docker runs at **15.6 FPS, 87 s per
case**, half real time: usable for batch reconstruction, and four times slower than the
number first given for it, which was measured on the host (ledger correction, DEBT). And
the check is manual: nothing in CI starts the stack, so a change that breaks it is found
the next time someone does this by hand.

## Owed

- Container CPU throughput (thread count, the Linux aarch64 wheel), if Docker speed matters.
- A CI job that builds both images, at least, so a broken Dockerfile is caught on push.

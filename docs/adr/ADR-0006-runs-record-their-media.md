# ADR-0006: A run records the clips it processed, and the API serves them for replay

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

The synchronized replay (E8.2) plays a case's three camera clips on one clock. To do
that the API has to know, for the run behind a case, which clip each camera's
observations were read from. Nothing records that today:

- `ProcessingRun` (frozen in PS-4) stores an `input_hash` of the clips, not where they
  are. A hash identifies a media set; it cannot locate one.
- `Camera.source_uri` is one value per camera for all time, not per run. Two runs over
  different cases would share it.
- The worker knows the case directory while it runs and forgets it afterwards.

Two ledger rows are waiting on the same missing field: E6.2 (the rewind gathers clip
references) and E8.2 (the replay itself). A third, the analytics debt from E8.6, needs
to know when footage was captured: incidents carry run-relative seconds, so there is
no calendar to find a recurring pattern on.

Changing a contract needs a `SCHEMA_VERSION` bump, this ADR and regenerated golden
fixtures (`CLAUDE.md`, schema authority).

## Decision

`ProcessingRun` gains two optional fields, and `SCHEMA_VERSION` goes from 1.0.0 to
1.1.0:

- `media_uris: dict[str, str]`: camera id to the clip that camera's observations were
  read from. Written by `process_run` from the clips it actually decoded, so the record
  cannot disagree with the processing.
- `captured_at: datetime | None`: the wall-clock moment the run's shared timebase
  starts. `None` for rendered cases, which have no real capture time.

The API serves footage through one endpoint, `GET /cases/{id}/media/{camera_id}`, which
resolves the run's recorded clip, refuses anything outside the samples root, and streams
it with range support so a browser can seek. `GET /cases/{id}/replay` returns the
window, the trigger time and, per camera, the media URL, clock offset and frame rate.

## Alternatives considered

| Option | Why not |
|---|---|
| Find the clips by matching `input_hash` against the dataset manifest | No contract change, but it hashes every clip on each replay request and breaks the moment footage is not in the manifest, which is every real deployment |
| Per-run `source_uri` on `Camera` | A camera is a fixed device; making it per run turns one camera into many rows and changes more contracts than it saves |
| Mount `data/samples` as static files | Serves the ground truth sitting beside the clips (`observations_gt.json`, `cause_gt.json`) to any browser, and leaves no single place to put the raw-video access control E10.3 requires |
| Signed object-storage URLs now | The private Supabase buckets exist, but uploading footage is deployment work (E10); a media URI can hold a storage key later without another contract change |

## Consequences

- **Easier:** the replay, the rewind's clip references (E6.2) and a later calendar trend
  in analytics all read one recorded field instead of re-deriving it.
- **Additive:** both fields are optional, so every 1.0.0 document still validates.
  Runs processed before this change have no `media_uris`; their replay says there is no
  recorded footage and to reprocess, rather than guessing.
- **One door for raw video:** every frame a browser sees passes through the media
  endpoint. E10.3 adds the role check and writes `evidence_access_log` there, and
  nowhere else has to change.
- **Harder to reverse:** removing the fields later is a breaking, major bump.

## Validation plan

- Integration tests: a run's recorded clips are served with `206 Partial Content` for a
  range request, and a recorded path outside the samples root is refused.
- Browser check now, Playwright in E9.4: after a seek, all three panes show the same
  shared-timebase instant, within one frame (0.1 s at 10 fps).
- Gate 6 walkthrough: clicking a timeline event moves all three cameras to that moment.

## Related

E6.2 and E8.2 ledger rows · ADR-0003 (Supabase storage buckets) · E10.3 security pass.

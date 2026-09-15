# Security and privacy

What specification §M asks for, and where each line of it is met. Read this before
putting the system in front of anyone but yourself.

| §M | Where |
|---|---|
| No face recognition | Charter §4 non-goal. The detector classifies four object classes; no model here embeds or matches faces, and the report says so on every copy. |
| Only legally usable video | The dataset is entirely simulated (`docs/dataset/`, risk R11). Any real footage is the operator's responsibility to have the right to process. |
| Raw video separated from derived metadata | §1 below: the `analyst` role never receives a frame. |
| Role-based access before multi-user deployment | §1: HTTP Basic, two roles, `ADR-0009`. |
| Access to sensitive evidence logged | §2: an append-only audit table and a structured log event. |
| Retention and deletion rules | §3. |
| Not an autonomous adjudicator | README "Responsible use", and the closing sentence of every report's limitations. |
| Reports state limitations and uncertainty | `Report.limitations` is required and never empty (contract); gaps are first-class claims (E7.3). |

## 1. Accounts and the one boundary

Every endpoint but `/health` needs an account. Accounts come from `REWIND_USERS`,
comma-separated `name:password:role`:

```bash
REWIND_USERS="ana:correct-horse:analyst,ivo:battery-staple:investigator"
```

| Role | Reads | Changes |
|---|---|---|
| `analyst` | Case inbox, case detail, timeline, evidence graph, hypotheses, report, runs, metrics | none |
| `investigator` | Everything an analyst reads, **and footage** | Create a case, change its status, reprocess it |

That is the whole boundary: the raw video on one side, everything derived from it on
the other. An analyst opening a case sees the replay panel say footage is restricted,
and the timeline, graph and report in full. There is no third role, and no
self-service user management: two lines in an environment variable is the size of
the need, and user management is a charter non-goal.

**Demo accounts.** The compose stack and `make api` ship `investigator:rewind` and
`analyst:rewind` so Gate 6 needs no secret. Change them in `.env` before the UI is
reachable by anyone else. The API refuses to start with no accounts configured.

**Transport.** HTTP Basic sends the password with every request. On a laptop, over
`localhost`, that is fine; anywhere else, the UI's origin must be TLS. The compose
stack publishes only the UI port, and the API is reached through it.

**Signing out** is closing the browser; Basic credentials live in the browser's memory
for the session.

## 2. What is logged

Every read of footage, of the evidence graph and of the report writes one row to
`evidence_access_log` — who (`actor`, `actor_role`), what (`resource_type`,
`resource_ref`: the camera for footage, the case otherwise), which case, and when —
in the same transaction as the read. The table is append-only by intent: nothing in
the codebase updates or deletes from it, and `scripts/maintenance/delete_run.sql`
leaves it alone when a case is deleted, so "who looked at this evidence" outlives the
evidence.

The same fact goes to the log stream as an `evidence access` line. With
`REWIND_LOG_FORMAT=json` (the containers) it carries `action=evidence.access`, `user`,
`role`, `resource`, `case_id` and `camera_id` as keys, so an aggregator can filter on
them; at a terminal it reads as a sentence.

```sql
-- Who watched CAM_A of a case
SELECT accessed_at, actor FROM evidence_access_log
WHERE incident_id = 'INC-RUN-case_01-01' AND resource_ref = 'CAM_A'
ORDER BY accessed_at;
```

One row per request, not per viewing: a browser scrubbing through a clip fetches it
in ranges, so one sitting with CAM_A can leave several footage rows. The question the
table answers is "did this account read this evidence, and when", and that it answers
exactly.

What is **not** logged: inbox and timeline reads (metadata, not evidence), and the
request log's client addresses, which uvicorn writes as it always did.

## 3. Retention and deletion

What the system holds, and how long:

| Data | Where | Retained | Deleted by |
|---|---|---|---|
| Footage | Files under `data/samples/`, never copied into the database; a run records their paths (`ADR-0006`) | As long as the files exist | Removing the files. A case whose clip is gone still opens; its replay pane says the footage could not be loaded |
| Observations, tracks, links, events | Database, keyed by run | Until the run is deleted | `scripts/maintenance/delete_run.sql` |
| Incidents, evidence graph, hypotheses, reports | Database, keyed by incident, which belongs to a run | Until the run is deleted | Same script. Reports are immutable while they exist; a dismissed case keeps its report as issued |
| Evidence access log | Database | **Indefinitely** | Never by the application. An operator who must purge it (a subject-access deletion, a retention law) does so by hand and records why |
| Application logs | The container's stdout; wherever the aggregator keeps them | The aggregator's policy | The aggregator |
| The whole local stack | The `pgdata` volume | Until discarded | `docker compose down -v` |

Rules:

1. **Nothing is deleted automatically.** There is no retention job; a run stays until
   an operator deletes it. The dataset is simulated, so the MVP has no legal clock to
   run against. A deployment on real footage must set one and schedule the script.
2. **A run is the unit of deletion.** Delete the run and everything derived from it
   goes; the foreign keys do not cascade, so nothing deletes a run by accident:

   ```bash
   psql "$DATABASE_URL" -v run=RUN-case_01 -f scripts/maintenance/delete_run.sql
   ```

3. **Footage and its derived record are deleted separately**, on purpose. Deleting a
   run does not touch the clip; removing the clip does not remove the run. The report
   stands as an account of what was seen even after the video it cites is gone.
4. **The access log is kept when the evidence is deleted.** It is the record that the
   evidence existed and who read it.
5. **Reprocessing does not delete.** A run is identified by its inputs, dataset,
   config and model versions (E2.2, `services/ingestion/registry.py`); a rerun with
   different versions is a new run beside the old one, and the old one is deleted by
   rule 2 if it should go.

## 4. Responsible use

The README's statement, in full:

> - Face recognition is **not** a feature of this system and will not be added.
> - Only public, synthetic or explicitly permitted video is used. The MVP dataset is
>   entirely simulated.
> - REWIND is a decision-support tool. It must not be used as an autonomous
>   disciplinary, legal or safety adjudicator.
> - Every generated report states its own evidence limitations and uncertainty.

Every generated report ends its `limitations` with the same commitment, so a report
read apart from the system carries it:

> Responsible use: this report is decision support for a human investigation. It must
> not be used as an autonomous disciplinary, legal or safety adjudicator. It
> identifies no person; entities are tracked objects, never faces.

## Related

`ADR-0009` (the boundary in the API) · `ADR-0003` (Supabase RLS, still deny-all) ·
`ADR-0006` (runs record their media) · `apps/api/auth.py` ·
`packages/database/models.py` (`EvidenceAccessLog`) · specification §M.

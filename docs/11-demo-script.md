# Demo script

An end-to-end recording of about eight minutes, from `docker compose up` to a report
that says *Cannot determine* about an interval no camera saw. The UNKNOWN interval is
the headline, not an apology: every other system in this space shows you video; this
one tells you what the video cannot establish.

Record on the compose stack, not the dev servers, so what is shown is what a stranger
gets from the README. Roles: `investigator:rewind` for most of it, `analyst:rewind`
for one scene.

## Before recording

```bash
docker compose down -v            # a clean database, so the inbox starts empty
docker compose up --build         # wait for "worker … waiting for jobs"
```

Have two terminals visible: one with the compose log, one for `curl`. Set the
browser to a 1440-wide window; the case page's three panes need the width. Close
other tabs on `localhost:5173` — a stale Basic session will skip the sign-in you want
on camera.

Queue both cases before you start talking; on CPU each takes about ninety seconds
(`case_02` a little longer), and the inbox filling in while you show System Health is
part of the story:

```bash
curl -u investigator:rewind -X POST localhost:5173/api/v1/cases \
  -H 'Content-Type: application/json' -d '{"dataset_version": "v1", "case_ref": "case_01"}'
curl -u investigator:rewind -X POST localhost:5173/api/v1/cases \
  -H 'Content-Type: application/json' -d '{"dataset_version": "v1", "case_ref": "case_02"}'
```

## Scenes

### 1. What this is (0:00–0:45)

Over the compose log. *Three fixed cameras in a simulated warehouse, four kinds of
entity, two incident classes. When a robot emergency-stops, or a zone stays blocked,
REWIND rewinds the footage across the cameras, builds an evidence graph, ranks the
candidate causes, and writes a report in which every material claim cites evidence and
every interval no camera saw is stated as such. No LLM anywhere in that path.* Point at
the log: one API, one worker, Postgres, Redis, nginx. Nothing else.

### 2. Sign in and System Health (0:45–1:30)

Open `http://localhost:5173`. The browser prompts; sign in as `investigator`. Show
the header: `investigator · investigator`. Go to **System health**: queue depth,
worker heartbeat, frames per second and peak memory arriving from the first run,
evidence coverage and unsupported-claim rate as "not measured" until a report exists.
*Null means not measured. A zero here would be a claim the system cannot back.*

### 3. The inbox fills (1:30–2:00)

Back to **Cases**. `case_01`'s incident appears: *Robot e-stop after human incursion*,
severity High. Filters by severity and status. Open it.

### 4. Synchronized replay (2:00–3:00)

Three panes on one clock. Press play; scrub; step a frame. Say the offsets: CAM_B and
CAM_C carry their own clock offsets and the player corrects each pane past a frame of
drift. Click **Go to detection**: all three seek to 13.4 s, the e-stop.

### 5. Timeline → cameras (3:00–3:45)

**Timeline** tab. Entity lanes per camera, event ticks, the trigger line. Click the
person's `zone_entry` into the robot lane; every camera seeks to it, and the inspector
on the right shows the event with its evidence refs and the identity links behind it.
*Clicking evidence is how you check the system, not how you browse it.*

### 6. Evidence graph (3:45–4:30)

**Evidence graph** tab. Nodes styled by evidence state: solid observed, dashed likely,
dotted possible, hatched unknown. Click the trigger event, then the candidate-cause
edge to the entry. Provenance on the inspector: which observation rows the node came
from. *Every node and edge points at a stored row. There is nothing in this graph the
database cannot show you.*

### 7. The report, and its vocabulary (4:30–5:15)

**Report** tab. Summary; claims each with a level and a reference; ranked hypotheses
with support **and contradiction** refs; limitations ending with the responsible-use
sentence. Click a reference: the graph node it names is selected and the cameras seek.
*"Observed", "Likely contributed", "Possible", "Cannot determine": the generator can
only say what the evidence level allows. A claim at any level above unknown with no
reference fails validation before it can be written.*

### 8. The UNKNOWN interval — case_02 (5:15–6:45)

Back to the inbox; open `case_02`. This is a held-out case, opened once in Week 17
under a pre-registered protocol. **Timeline**: the *Unseen / undecided* lane carries a
hatched interval — the person is behind the forklift and no camera has them. Click
it: the cameras seek to the start of the gap and show exactly that. **Report**: the
*Cannot determine* claim citing that gap by id, and nothing ranked above *Possible*.
*This is the thesis. The system does not fill the gap with a guess. It names it, cites
it, and lowers every conclusion that depends on it.*

Say plainly, on camera: on this case the detector finds the person in 6.5 % of the
frames the ground truth counts, so with real detections the person is not ranked as a
cause at all — the report says the interval cannot be determined and stops there. With
perfect tracks (`tests/e2e/test_golden_case.py`, and `C01-report-tracks.md` for the
shape of it) the same case ranks the person *Possible*, "while no camera saw it". The
held-out benchmark fails five of the charter's perception floors; the reasoning layer
passes its behaviours anyway. Numbers and failure frames:
`artifacts/benchmark-reports/final.md`, `docs/failures/`.

### 9. The role boundary (6:45–7:15)

New private window; sign in as `analyst`. Open `case_02`: the three panes say *Raw
footage is restricted to investigators*; the timeline, graph and report are intact.
Try to change the status: *Not saved: analyst is an analyst; footage and changes need an
investigator*. In the terminal:

```bash
docker compose exec db psql -U rewind -c \
  "select accessed_at, actor, resource_type, resource_ref from evidence_access_log order by accessed_at desc limit 5"
```

*Every read of footage, graph or report is a row. It outlives the evidence.*

### 10. Reproducibility and close (7:15–8:00)

Over the terminal. `make bench` regenerates the benchmark report; the run records the
input hash, dataset, config and every model and component version; `POST
/cases/{id}/reprocess` runs the same footage under another config beside the old run.
Close on the deviation ledger: seventy-odd classified departures from the plan, with
what each cost. *The plan was not followed. It was measured against.*

## If something goes wrong

- Worker slow: it is CPU in Docker; the number is in the README. Cut to a case that
  has finished.
- A pane says footage could not be loaded: the clip path is not under `data/samples`;
  `make fetch-data` and reprocess.
- Sign-in loops: the browser holds an old Basic session; use a private window.
- No incident for `case_02`: check `docker compose logs worker` for the run's error;
  the run is marked FAILED with the reason, never silently queued.

## Assets

Screenshots for the deck go in `artifacts/demo-assets/`. The two C01 reports there
(`C01-report-detections.md`, `C01-report-tracks.md`) are the Gate 4/5 walkthrough
material and are the fallback if the live report cannot be shown.

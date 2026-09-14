# Gates 4 and 5 — walkthrough with the mentor

- **Sub-phase:** E7.5, the item a test cannot close: a person reads a C01 report against
  its footage.
- **Rehearsed:** 2026-09-14, on the real pipeline's C01 (`INC-RUN-case_01-01`)
- **Mentor session:** _not yet held_
- **Why before E9.1:** anything this session changes in reasoning or wording is changed
  while `case_02` and `case_06` are still sealed, so the golden numbers stay held-out.

## Setting up

On the machine that already processed the tune cases (the local `rewind_dev` database):

    DATABASE_URL=postgresql+psycopg://t:t@localhost:5434/rewind_dev make api
    make web
    # open /cases/INC-RUN-case_01-01

On a clean machine, through the product path, with `DATABASE_URL` in `.env` pointing
at an empty Postgres and case_01 rendered (`make render`):

    make up && make migrate
    make api            # terminal 1
    make worker         # terminal 2
    make web            # terminal 3
    curl -X POST localhost:8000/api/v1/cases -H 'Content-Type: application/json' \
      -d '{"dataset_version": "v1", "case_ref": "case_01"}'
    # when the run completes, open the case from the inbox

## The walk

Open the report view. For each row, click the citation named, watch the three cameras
move, and check the footage against the claim. The person is the green figure, the robot
the white one. Z2 is the intersection floor, Z1 the robot lane crossing it.

| # | Click | All cameras should land at | Check in the footage | Rehearsal | Mentor |
|---|---|---|---|---|---|
| 1 | `EVT-…-TEL-0001` on "Observed: robot R12 reported an emergency stop" | 13.4 s | Robot beside the person at the intersection; stepping frames forward, it does not move | All three at 13.40 s; robot at the intersection next to the person. The claim cites telemetry, and the inspector says "telemetry, not video" | ☐ |
| 2 | `EVT-…-CAM_C-0006` on "Observed: Person entered Z2" | 11.6 s | Person at the edge of the intersection floor, stepping in | 11.60 s; CAM_C shows the person entering the floor from the south | ☐ |
| 3 | `EVT-…-CAM_C-0004` on "Observed: Person entered Z1" | 12.8 s | Person reaching the robot lane | 12.80 s; person at the lane's edge in all three views | ☐ |
| 4 | `…/H01` on the ranked cause | 11.6 s | The approach the cause rests on | 11.60 s, see observation A | ☐ |
| 5 | `…/G001` on "Cannot determine: … between 3.4 and 9.9 s" | 3.4 s; then scrub to about 6.6 s and 9.8 s | No camera gives a usable view of the person | Person absent at 6.6 s; slivers at the window edges, see observation B | ☐ |
| 6 | `…/C001` on "Cannot determine whether CAM_A-T004 and CAM_C-T002 are the same person" | 10.7 s | How many people are in the scene | 10.70 s; one person, visible in all three. See observation C | ☐ |

Then, in any view: is every conclusion reachable from its evidence in one or two clicks?

## Observations from the rehearsal, for discussion

**A. A ranked cause seeks to its first supporting moment, the Z2 entry at 11.6 s, not the
Z1 entry at 12.8 s.** The seek takes the first cited moment, which is the approach. If the
mentor would rather land on the decisive event, that is a small UI change and does not
touch scoring.

**B. The gap's edges are softer than its wording.** At 3.4 s a few pixels of the person
show at CAM_A's left edge, behind a rack; at 9.8 s the person is entering CAM_C's bottom
edge while the report says unseen until 9.9 s. Ground truth puts the gap at 2.9–9.6 s.
Boxes cut by the frame edge below 16 px are dropped (`edge_min_side_px`, EXP-0004), so
"no camera saw it" means no usable view, and its boundaries move by up to half a second.
Worth asking whether the report should say so.

**C. The identity conflict is obvious to a person and undecided for the system.** There
is one person in case_01. The system linked their three tracks through two comparisons
but refused the third directly, and says it cannot determine that pair. This is the
understatement accepted as option A in `gate-4-5.md`; the footage makes the cost
concrete. It is not to be tuned before E9.1.

**D. Found while preparing, and fixed:** a clean database could not process a case,
because nothing registered cameras outside the tests (ledger, BUG-FIX). The clean-machine
setup above depends on that fix.

## Questions for the mentor

1. Does each claim's wording match what the footage shows?
2. Does the report claim anything the footage contradicts?
3. Does the footage show anything material the report leaves out?
4. Observations A to C: change now, while the golden cases are sealed, or leave?

## Sign-off

| | |
|---|---|
| Mentor | |
| Date | |
| Verdict | |
| Changes agreed before E9.1 | |

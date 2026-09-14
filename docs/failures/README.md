# Failure catalogue (E9.2)

Every failure mode the pipeline has shown, with a root cause and where it stands. One
row per mode, not per occurrence; the experiment record named holds the trace. Frames
are captured by `scripts/evaluation/capture_frame.py`: green boxes are ground truth
with the entity id and its visibility, red boxes are the detector's with class and
confidence. Green without red is a miss; red without green is a false box.

**Status** means: *fixed* (rule or model changed, re-measured); *accepted* (recorded
as a limitation, with the design's answer to it); *carried* (owned by a later phase or
a re-render); *partial*.

## Perception

| # | Failure mode | Frame | Root cause | Found | Status |
|---|---|---|---|---|---|
| P1 | A partially occluded person is detected twice: the visible part and the full extent, IoU ~0.65, both kept by NMS 0.7 | `../gates/gate-1-duplicate-detection.png` | COCO-tuned NMS default meeting a scene where one object detected twice is likelier than two objects at that overlap | Gate 1, EXP-0004 | fixed: NMS 0.5 |
| P2 | An actor rising into view from a frame edge is a 4 px, then 13 px sliver; each opens a new track | — | Boxes cut by the edge grow too fast between frames for ByteTrack to match, and their centre is not the entity's | Gate 1, EXP-0004 | fixed: `edge_min_side_px` 16 |
| P3 | A person unseen for 7.9 s returns as a new track | — | A box-only tracker's Kalman prediction drifts too far to re-match | Gate 1 | carried to E5 appearance; remains as the identity refusal in I3 |
| P4 | A forklift and its pallet are one track while carried | — | Geometrically one moving object | Gate 1, EXP-0002 | accepted |
| **F1** | A forklift of a colour absent from the tune data is never detected (0 of 697, visibility to 0.93) | [F1-case_06-CAM_C-f130.jpg](F1-case_06-CAM_C-f130.jpg): navy F02 (vis 0.95) has no red box; red F01 beside it is found at 0.94 | The fine-tuned detector learned *forklift* as F01's colour; no tune case has a second forklift colour | E9.1, EXP-0010 | carried: colour-blind v2 finds F02 but loses the frame-cut forklift (F4's view); not promoted; next attempt an E1 re-render with a second forklift colour in a tune case (EXP-0011) |
| **F2** | A person at a fifth of their silhouette behind a vehicle is not detected (4 of 297) | [F2-case_02-CAM_A-f149.jpg](F2-case_02-CAM_A-f149.jpg): P01 (vis 0.21) is a sliver beside the red forklift | Ground truth emits boxes from 0.15 visibility; recall on a fifth of a silhouette is not a capability the tune data teaches | E9.1, EXP-0010 | accepted: the unseen interval is claimed as *Cannot determine* (F6) |
| **F4** | A forklift half outside the frame gets a second box on its dark front face (IoU 0.27, under NMS), which seeds its own track and is linked across cameras | [golden-case_02-CAM_B-f112-duplicate-box.jpg](../../artifacts/benchmark-reports/golden-case_02-CAM_B-f112-duplicate-box.jpg) | Two boxes of one class on one object at low overlap; NMS cannot see it | E9.1, EXP-0010 | partial: nested same-class boxes dropped (`nest0.9`, EXP-0011); the front face detected *alone* still starts a track, and its links stay (I4) |

## Events and localisation

| # | Failure mode | Root cause | Found | Status |
|---|---|---|---|---|
| E1 | A 2.2 m forklift seen from the steep camera is placed up to ~1 m along its length; zone entry 0.8 s early, exit 2.5 s late on that camera | Single-point back-projection of a box centre | Gate 2, EXP-0005 | carried to E5 fusion; the merge across cameras takes the earliest crossing |
| E2 | A 38 %-visible person at 16 m yields a fragment box a metre off: one confident wrong exit | Fragment centre is not the entity's | Gate 2, EXP-0006 | accepted |
| E3 | Two same-class entities entering one zone within 0.8 s from different cameras merge into one event | Merge by class and time, before identity | Gate 2 | accepted; identity links (E5) do not reach the extractor |
| E4 | Configured camera clock offsets were wrong for the rendered clips and silently applied since E2 | Offsets copied from the scene design, not measured from the render | Gate 2 closing | fixed: E5.1 clock check, re-tuned merge window |
| **F3** | A still object on a zone edge flickers in and out, and the report says *Observed: entered* | [F3-case_02-CAM_A-f146.jpg](F3-case_02-CAM_A-f146.jpg): F01 parked at y = 9.5, Z1's edge; its projected position wobbles up to 0.4 m on real detections | Zone transitions taken from raw back-projected positions with no margin | E9.1, EXP-0010 | fixed: `confirmed_transitions`, 0.5 m by depth or movement, margin from tune-case wobble (EXP-0011). Cost: a vehicle that noses 0.2 m over an edge and reverses is no longer a crossing (case_06); carried by F7 |

## Identity

| # | Failure mode | Root cause | Found | Status |
|---|---|---|---|---|
| I1 | Viewpoint changes an entity's colour distribution: a pallet from the steep camera (appearance 0.02), a person from two angles (0.40) are refused despite good geometry | Colour-histogram descriptor is not viewpoint-invariant | Gate 3, EXP-0007 | accepted: recall cost, never a false link |
| I2 | An edge-cut entity has neither a usable position nor a usable crop | Fragment at the frame edge | Gate 3 | accepted: refused in every mode, correctly |
| I3 | A fragmented track leaves two segments close enough in score that the ambiguity rule refuses one hand-over; the report then words the flagship cause *Conflicting evidence* and names a false gap on the unlinked fragment | Refusal is the design's answer to ambiguity (option A, Gate 4/5) | Gates 3–5, EXP-0007, EXP-0009 | accepted by owner decision; wording errs toward saying less |
| I4 | A track that is a fragment of a real forklift (front face alone at the frame edge) is linked to that forklift on the other cameras: 2 false links, rate 0.29 on the golden pair | Appearance is the forklift's own colour; geometry is plausible | E9.1, EXP-0011 F4 | carried: candidate rule, refuse an edge fragment (short, at the edge, one camera), thresholds from tune cases |

## Reasoning and report

| # | Failure mode | Root cause | Found | Status |
|---|---|---|---|---|
| **F5** | No hypothesis for an entity whose decisive move was unseen: the case the project is named for got a forklift ranked *Possible* and no person | The extractor emitted the bounded entry stamped at the reappearance; the ranker judged it by its stamp, after the window | E9.1, EXP-0010 | fixed: bounded events judged by the interval they happened in, worded "at some moment between … while no camera saw it", capped at *Possible* (EXP-0011) |
| **F6** | The unseen interval reached the graph and the limitations count but never a claim | *Cannot determine* written only for entities a hypothesis named | E9.1, EXP-0010 | fixed: any non-robot gap overlapping the look-back before the trigger is claimed (`deterministic-0.2.0`) |
| **F7** | A blocked zone's earlier contributor fell outside the window, and candidates came only from zone entries | Window opened before the *last* rest; no contact-based candidates | E9.1, EXP-0010 | fixed: window from the first of a chain of rests; candidates from proximity to the resting object (EXP-0011) |
| R1 | A pallet fragment ranked as a second, low candidate on case_04 | Identity refused to join the pallet's per-camera tracks, so a fragment looked like another object | Gate 4/5, EXP-0009 | fixed as a side effect of F7's amendment: the object is every same-class track resting in the zone while the trigger's does |
| R2 | Gate 5 guarantees every claim is traceable, not that the evidence it traces to is true (F3's false *Observed* claim cited a real event) | By design: the generator checks citations, not the world | E9.1, EXP-0010 | accepted; the defence is upstream (F3) and the *Observed* level's reservation for direct events |

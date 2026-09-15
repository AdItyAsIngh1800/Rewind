**Found on the golden cases, post-golden (EXP-0013).** Trained after EXP-0010 on the
three tune cases plus `case_07`, which shows a navy forklift cut by a frame edge; the
golden numbers below neither trained nor selected the model, but the case that did
was designed from the failure catalogue's description of them.

**A person at a fifth of their silhouette is still not detected.** `case_02`'s P01 behind
the parked forklift: 20 of 321 boxes (F2, accepted limitation). Person recall 0.062
against 0.065 for v1, with F02 now found: the postmortem's test that F2 is a visibility
limit and not a training gap, passed.

**Two forklifts can share one track on one camera.** On `case_06`'s CAM_A, F01 leaves the
view at 12.2 s and F02 enters nearby at 12.6 s, inside ByteTrack's 3 s buffer; the
tracker continues F01's id onto F02. The ID-switch metric counts an entity changing
track, not a track changing entity, so this is invisible to it (F8). A cross-camera
consumer of that track sees one forklift where there were two.

**A pallet being pushed splits and flips its track.** On the same camera, PL3 alternates
between two tracks four times in 1.3 s (20.9–22.2 s) while F02 pushes it into the
zone: four switches against a floor of two (F9). v1 never showed this because it never
detected the forklift doing the pushing. A tracker setting, not a detector one; it is
the cost of seeing F02.

**A forklift half outside the frame can produce a second box on its front face** (F4).
The nested-box rule (`nest0.9`) drops one inside a larger box; on `case_02` v3's boxes
are clean enough that no fragment track is linked across cameras, and the false-link
count there is 0 of the pairs compared.

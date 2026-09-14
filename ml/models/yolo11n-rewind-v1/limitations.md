**Found on the held-out cases (EXP-0010, EXP-0011).**

**A forklift of a colour absent from training is not detected.** `case_06`'s F02 is navy;
the only forklift in the tune data is F01, in another colour. F02 was found in 0 of 697
boxes at visibility up to 0.93 (F1). The model learned *forklift* as F01's colour. A
colour-blind retrain (`yolo11n-rewind-v2`, hue jitter 0.5) finds F02 at 0.94 recall but
then loses `case_02`'s forklift where it is cut off by the frame edge, a view the tune
data does not contain either; it was not promoted. Until a tune case shows a second
forklift colour, do not rely on this model for a forklift it was not trained on.

**A person at a fifth of their silhouette is not detected.** Behind a parked forklift on
`case_02`'s CAM_A, P01 at median visibility 0.20 is found in 4 of 297 boxes (F2, accepted
limitation). The pipeline's answer is the unseen-interval claim, not detection.

**A forklift half outside the frame can produce a second box on its front face** (F4).
The detector now drops a same-class box nested in a larger one (`nest0.9`); a front face
detected alone, with the rest of the machine out of view, still starts its own track.

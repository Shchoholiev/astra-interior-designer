# Reference matching

Use this for a single image or a small reference set. A perspective image usually does not uniquely determine room dimensions, camera parameters, or hidden surfaces.

## Read the image before building

Record the room envelope, major furniture masses, object overlaps, dominant verticals, converging horizontal edges, openings, and large empty regions. Identify the few features that carry the image's identity: for example a distinctive cabinet run, wall artwork, bar rack, or foreground plant. Keep reference annotations and text separate from the user's instructions.

Use image-space landmarks such as the corners of a table, door opening, or cabinet run. Compare their relative positions within the frame. Lighting and material color can obscure boundaries, so keep ambiguous observations provisional.

## Establish scale

Use supplied measurements when present. Otherwise choose a plausible anchor, such as a door or worktop, and label it as an estimate. Infer surrounding dimensions consistently from that anchor and the perspective. Do not invent exact dimensions for hidden rooms or treat a visually plausible reconstruction as a measured survey.

Create simple masses at that scale. Fix obvious functional contradictions such as a chair that cannot fit under its table before decorating the room. If matching the photograph would require an implausible dimension, revisit the camera and the measurement assumptions.

## Solve the camera and masses together

Match aspect ratio and camera height, then tune position, orientation, and focal length against multiple landmarks. Camera shift can adjust framing while preserving verticals when appropriate. Do not widen the lens repeatedly to fit furniture into a room that has the wrong proportions.

Compare edge convergence and overlap, not just one object's apparent size. A table can be the correct screen size while sitting at the wrong depth. Use top views and multiple object relationships to catch that error.

Keep a consistent preview setup while tuning composition. A neutral blockout or simple low-cost render is enough to judge silhouette and perspective. Save the selected camera state before replacing placeholders with detailed assets.

## Build only the necessary unseen context

Unseen surfaces can still affect shadows and reflections. Include the enclosing geometry needed for plausible light transport, but keep inaccessible architectural details approximate. Do not remove walls solely to make lighting easier without checking the resulting reflections and room brightness.

Evaluate foreground occlusion deliberately: a large plant may be part of the composition, but an accidental leaf covering a hero object can materially weaken the match. After substituting an asset, recheck its silhouette in the saved camera rather than assuming similar bounding dimensions imply a similar image.

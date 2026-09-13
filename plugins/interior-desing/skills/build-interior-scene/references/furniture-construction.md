# Furniture construction and placement

Use for custom furniture, a replacement hero asset, or a targeted upholstery or placement correction. Work from the user's reference and preserve features already accepted. A firm upholstered dining chair and a loose lounge cushion need different shapes; additional softness is not a universal improvement.

## Separate the shape controls

Read the silhouette in front, side, and three-quarter views where references permit. Record which features are observed and which are estimated. Distinguish:

- Backrest lean, curvature along its height, wrap across its width, thickness, and corner radii. Tilting a flat slab does not create a curved back.
- Seat plan outline, top crown or depression, underside curve, and thickness across the whole profile. A pronounced lower arch can coexist with an almost flat top.
- Upholstery volume and the supporting frame or legs. When the reference has a separate seat and back, preserve that construction instead of rounding them into one plush mass.

Keep these controls independent when modeling. Broad subdivision or a uniform bevel can round approved corners, inflate a firm seat, or erase a panel transition. Check the evaluated silhouette after modifiers rather than only the base mesh.

For "make the seat thicker, otherwise good," measure front, middle, and rear thickness. If the top and seat height are accepted, add volume downward and retain their shape. Recheck the underside, leg insertion, floor contact, and table clearance. Do not increase the top crown just to obtain thickness. A request to reduce the top bend likewise need not flatten an intentional underside arch. Dimensions from a previous chair are examples, not defaults for new furniture.

## Follow the cover construction

Identify the broad cover, side panels or gussets, and any continuous wrap over the top before adding detail. Distinguish a recessed panel join from visible thread stitches and raised piping. The user's word "stitch" may refer to the visible join; use the supplied example or annotation to determine what is actually shown.

Trace the route on the correct surface, including its turn around a corner and continuation over the top. An outline inset into a narrow side face will not reproduce a join located on the broad face beside the rolled edge. Preserve a continuous cover where shown instead of inventing a seam across it. A marked path establishes placement; its drawn line width is not a physical seam-width measurement.

Model a join as a restrained recess or panel transition when that is the visible construction. Add discrete thread segments or piping only when the reference or requested finish calls for them; a continuous raised tube does not become stitching by being named that way. Keep details attached to the evaluated surface through corners, without floating, doubling the border, or creating an unintended hard crease. Judge a close-up and the delivered view before increasing depth or contrast.

Localized folds should taper from plausible joins, compression, or bends and follow the cover's tension. A taut panel can remain mostly smooth. Keep these folds distinct from fine leather grain using [leather guidance](../../cycles-materials/references/surfaces.md#leather-and-upholstery).

## Refine one asset before replacing repeats

For a substantial furniture rebuild, use a separate studio scene or isolated collection in the same Blender process. Keep the main room recoverable. A small local repair does not require this full staging workflow.

Use a side profile to assess curvature and thickness, a three-quarter render for volume, and a close-up of the disputed join or surface. Compare with the supplied reference and the previous accepted version under consistent settings. Resolve the requested construction defects before propagating the asset; a neutral studio helps diagnosis but does not establish that the material works under the room's lighting.

Save the corrected asset and append or link that exact version into the room following [asset integration](asset-integration.md). Preserve placement parents and approved transforms unless rearrangement is requested. Use shared component meshes for intended repeats, isolate exceptions, and check that old and replacement parts are not both visible. After import, verify the room camera and lighting, material dependencies, support, and the final room image.

## Place chairs in relation to the table

Inspect a top view and express placement relative to the table's orientation and edges. World-axis alignment can leave chairs skewed against a rotated table. For an orderly dining arrangement, use a consistent facing direction toward the relevant edge, spacing along it, and tuck depth. Preserve a deliberate angle or asymmetry when the reference or user calls for it; do not add random rotation as a realism treatment.

Check the usable relationship: seat height relative to the tabletop and apron, clearance around table legs, access to sit down, and space to pull a chair out. Feet must meet their actual supporting surface. Inspect evaluated geometry for intersections, then judge the room view; passing collision checks alone does not establish a natural arrangement. Keep inferred ergonomic dimensions provisional when measurements are unavailable.

Change only the requested placements. After a shared chair asset changes, recheck all its instances for support and clearance even if only two chairs were rearranged.

## Examples of rejected and corrected choices

These describe the dining-chair refinement that motivated this guidance. Use the decision criteria, not its exact dimensions or seam position, for another design.

| Rejected appearance or action | Correction to test | Evidence to compare |
| --- | --- | --- |
| Flat back tilted backward to imitate curvature | Shape the back profile separately from its lean | Side silhouette and three-quarter view |
| Firm upholstery becomes plush, with inflated corners | Reduce the demonstrated excess crown or edge rounding while preserving the intended volume | Corner crop and whole chair against the reference |
| Thin seat center; thickening also exaggerates its accepted top bend | Adjust the lower profile independently | Front/middle/rear thickness and matching side crop |
| An inset border is placed on the side panel when the marked join lies on the broad cover | Trace the actual panel boundary around the corner | Reference or annotation beside the rendered join |
| Collision-free chairs still look awkward beside the table | Correct their facing, spacing, and tuck depth in table coordinates | Top view, usable clearances, and room render |

Keep actual rejected and corrected crops in the task's output record when available, tied to their native asset revisions. These textual examples do not replace visual evidence or prescribe the same shape for every chair.

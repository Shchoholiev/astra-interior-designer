# Asset integration

Use for downloaded models and append/link operations. Importing is a scene mutation; asset search or a verified download alone does not establish import success.

## Before import

Keep the source files and provenance in a stable task asset directory. Check that the package contains its referenced buffers, textures, and material files. A glTF JSON file without its required buffers is incomplete. Inspect optional compression requirements and use the target Blender version's supported importer.

Inspect the asset in a dedicated collection in the current Blender session. For a `.blend`, append the required asset collection or objects and their dependencies; do not open the whole author scene over the current project merely to obtain a plant. Avoid importing unrelated cameras, world settings, or light rigs. Retain supporting objects genuinely required by modifiers, instances, or node groups.

## Normalize placement without damaging the asset

Measure the imported hierarchy's evaluated bounds, orientation, parent transforms, and scale. Unit conventions and root rotations can make a correct model appear sideways or enormous. Choose an explicit physical dimension from the brief or a stated estimate before rescaling; never fix every import by an assumed factor of 100.

Use a placement parent when practical to preserve internal geometry, atlas UVs, rigs, and local relationships. Apply transforms only where their effect on modifiers, normals, and shared data is understood. Position using actual contact geometry: chair feet on the floor, pot bottom on the shelf, and table legs below the top.

Check both viewport and render visibility, collection exclusion, linked data, and instancing. Preserve authored material slots and vertex attributes. Keep an untouched source collection hidden from render when it is useful for later corrections, or rely on the preserved source package without duplicating large meshes unnecessarily.

## Support and assembly connections

Use bounding boxes for initial placement, then identify the actual supporting surface. A tray's highest bound can be its outer lip rather than its interior floor; placing fruit at that height leaves a visible air gap. Inspect evaluated geometry in a side or section view and, where useful, sample the contact region with rays restricted to the intended support mesh. Confirm hits land on the correct interior surface rather than a rim or unrelated object. For an uneven base, check the contact footprint instead of relying on one origin or bounding-box corner.

Move the complete supported assembly, including attached leaves, stems, handles, or decorations. Check contact and neighboring intersections again after rotation, scaling, or a support-shape change. A small numerical separation to avoid penetration must not become visible levitation. Verify the contact in a rendered close-up and side view; zero mesh intersections alone does not establish support or physical stability, and sampled checks are not a physics simulation.

Before rearranging parts inside an imported asset, identify logical assemblies across all its material meshes. A single flower can have its center in one object and petals in another; grouping connected components independently within each object can send petals to the wrong bloom. Use the untouched source coordinates and hierarchy to establish membership, transform the complete assembly together, and inspect petal roots, stems, and buds after the edit. Preserve a recoverable source when local sculpting makes the original relationships harder to infer.

When changing a leaf or petal's shape, retain its attachment point where the intended construction requires it. If the whole flower or leaf moves, verify and adjust its connecting stem within scope. Check these relationships after posing, alongside the final camera silhouette; a more attractive outline can conceal a detached component. Open petal or leaf surfaces are not automatically defects, so compare against the source instead of demanding every organic mesh be watertight.

## Verify in context

Inspect a camera preview and a side or top view. Confirm scale, contact, silhouette, texture completeness, and that the room camera/light rig stayed intact. Organic assets need inspection for repeated forms and alpha-card edges; furniture needs plausible support, upholstery volume, and interaction with nearby geometry.

Do not globally replace a shared material to recolor one placement. Check shared mesh material slots, nested node groups, and image datablocks before making an individual object independent. Preserve the atlas when it encodes seams and folds.

Record imported object/collection names, chosen physical size, placement transform, source identifier, and any conversion. Report an asset as import verified only after it loads correctly in Blender; describe visual substitutions honestly when it differs from the reference.

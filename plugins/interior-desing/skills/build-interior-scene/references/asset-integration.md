# Asset integration

Use for downloaded models and append/link operations. Importing is a scene mutation; asset search or a verified download alone does not establish import success.

## Before import

Keep the source files and provenance in a stable task asset directory. Check that the package contains its referenced buffers, textures, and material files. A glTF JSON file without its required buffers is incomplete. Inspect optional compression requirements and use the target Blender version's supported importer.

Inspect the asset in a dedicated collection in the current Blender session. For a `.blend`, append the required asset collection or objects and their dependencies; do not open the whole author scene over the current project merely to obtain a plant. Avoid importing unrelated cameras, world settings, or light rigs. Retain supporting objects genuinely required by modifiers, instances, or node groups.

## Normalize placement without damaging the asset

Measure the imported hierarchy's evaluated bounds, orientation, parent transforms, and scale. Unit conventions and root rotations can make a correct model appear sideways or enormous. Choose an explicit physical dimension from the brief or a stated estimate before rescaling; never fix every import by an assumed factor of 100.

Use a placement parent when practical to preserve internal geometry, atlas UVs, rigs, and local relationships. Apply transforms only where their effect on modifiers, normals, and shared data is understood. Position using actual contact geometry: chair feet on the floor, pot bottom on the shelf, and table legs below the top.

Check both viewport and render visibility, collection exclusion, linked data, and instancing. Preserve authored material slots and vertex attributes. Keep an untouched source collection hidden from render when it is useful for later corrections, or rely on the preserved source package without duplicating large meshes unnecessarily.

## Verify in context

Inspect a camera preview and a side or top view. Confirm scale, contact, silhouette, texture completeness, and that the room camera/light rig stayed intact. Organic assets need inspection for repeated forms and alpha-card edges; furniture needs plausible support, upholstery volume, and interaction with nearby geometry.

Do not globally replace a shared material to recolor one placement. Check shared mesh material slots, nested node groups, and image datablocks before making an individual object independent. Preserve the atlas when it encodes seams and folds.

Record imported object/collection names, chosen physical size, placement transform, source identifier, and any conversion. Report an asset as import verified only after it loads correctly in Blender; describe visual substitutions honestly when it differs from the reference.

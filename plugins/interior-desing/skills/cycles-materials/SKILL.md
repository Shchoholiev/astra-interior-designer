---
name: cycles-materials
description: Use when creating or repairing Blender Cycles materials for interiors, including plastic-looking upholstery, incorrect wood or stone texture scale, UV seams, glass, and foliage transparency. Applies to surface appearance and texture mapping rather than room layout or lighting design.
---

# Cycles materials

Create surfaces that fit the intended material, finish, and viewing distance. Diagnose the existing shader and mapping before replacing them. A plausible material cannot repair an incorrect silhouette or missing upholstery folds.

## Establish the target

Use the user's brief, reference, selected objects, and current render to identify the surfaces to change. For a new material, establish its finish and physical scale; for a repair, state the visible defect and likely cause.

When a complaint says the "scale looks wrong," distinguish object proportions from stretched mapping or incorrect texture feature size. Inspect the referenced region and mapping before proposing dimension changes; a grain-scale correction does not authorize resizing furniture.

Control Blender through the available Blender MCP connection. Discover the running Blender version, supported node sockets, and workspace paths. This skill needs native Cycles and local texture access; it has no external renderer dependency. If MCP is unavailable, report the connection issue without launching another Blender process.

For a material-only pass, retain the approved camera, geometry, lights, exposure, and color management. UV edits belong here. If geometry or lighting causes the defect, explain the necessary next step; complete independent material fixes within the requested scope.

## Inspect before changing

- Trace the target's assigned material from the output used by Cycles, including connected node groups. Inspect actual links rather than relying on node names or unconnected defaults.
- Identify shared meshes, materials, node groups, and images. Isolate the datablocks an edit would affect when other objects must retain their appearance. Changing an image's color space affects every user of that image.
- Inspect source images, channel roles, color spaces, texture coordinates, tangent-space normal UVs, and object dimensions with scene units. Read [mapping and texture checks](references/mapping.md) for image textures, UV defects, or imported PBR materials.
- Read the relevant section of [surface guidance](references/surfaces.md) for the material family being edited.

## Make the smallest effective change

Save a separate scene checkpoint before a material pass, retaining the previous render when available. Preserve useful atlas seams, folds, vertex colors, alpha masks, and native procedural detail. Use a suitable existing texture set or a calibrated procedural surface; acquiring new assets is a separate step when existing inputs cannot support the requested finish.

Correct wiring and mapping first, then tune surface response. Keep parameters tied to the reference and real dimensions. Update the intended nodes explicitly so rerunning the edit does not stack duplicate detail layers. Avoid blanket material replacement or global cleanup of unused source materials.

## Verify the result

Render a comparison crop or modest preview through the environment's existing render workflow. Keep the comparison framing, lighting, and color transform consistent. Wait for completion and inspect the actual image; queued work or a saved blend is not visual evidence.

Check the original defect, nearby highlights and seams, and objects sharing source assets. Confirm changed materials use supported Cycles nodes and required textures are readable. If rendering is unavailable, report the edit as visually unverified.

Save the revised native `.blend`, with required textures packed or stored at portable relative paths. Return links to the scene and comparison images, a concise explanation of the changes, verification performed, and remaining limitations. Keep each accepted pass recoverable.

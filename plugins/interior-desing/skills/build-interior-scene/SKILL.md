---
name: build-interior-scene
description: Use when blocking out or assembling a Blender interior, matching room proportions and camera framing to a reference, or importing and placing architectural elements, furniture, plants, and props. Applies to geometry and placement rather than material tuning or final lighting.
---

# Build an interior scene

Build the spatial structure that makes the intended view convincing: room proportions, object silhouettes, contact, and camera framing. Keep the scene editable so later material and lighting passes can target specific components.

## Inspect and block out

Use Blender MCP to inspect the current scene, units, active camera, collections, visibility, and existing assets. Preserve unsaved work in a separate recoverable checkpoint before replacing or switching a scene. Use the same connected Blender process and the runtime's safe loading routine when needed.

For image reconstruction, read [reference matching](references/reference-matching.md). For a measured room or design brief, use supplied dimensions and functional constraints first; estimate only the missing values and identify those estimates.

Create the architectural shell and major furniture volumes before details. Establish floor level, wall thickness, openings, and ceiling height. Compare a camera preview against the reference or brief. Correct perspective and relative size before compensating with implausible furniture dimensions. Use a top or side view to check spatial relationships hidden by the hero camera.

Keep the established camera for subsequent comparisons. Change it when composition is part of the task or a demonstrated camera mismatch needs correction, and save that as a distinct pass.

## Assemble usable geometry

Use named collections and component objects for architecture, furniture, plants, props, and lights. Preserve logical pivots and parent hierarchies. Reuse data for intentional repeats; isolate it when a local edit must not affect other instances. Stable names and an import record help scripts update existing objects without accumulating duplicates.

Model architectural pieces with credible thickness, softened edges, and contact surfaces. Inspect evaluated geometry, shading, and normals before adding subdivision. Limit detailed modeling to what affects the output; background objects need less detail than foreground upholstery or flowers.

Use [find-3d-models](../find-3d-models/SKILL.md) when a suitable existing asset would improve the requested object. Read [asset integration](references/asset-integration.md) before importing. Geometry or asset substitutions should preserve the user's constraints, not merely fill space.

Give visible clear windows an intentional outside view. For a fixed interior camera, a suitable exterior photograph on a plane beyond the glazing is a useful default. Read [window views](references/window-views.md) for sourcing, placement, and daylight interaction; a blank colored surface is not a finished exterior view.

## Verify the assembled scene

Check the final camera and at least one diagnostic view for floating feet, intersecting furniture, wall penetrations, incorrect plant scale, duplicated objects, and hidden render geometry. Compare large negative spaces and occlusions before adding small decorative props. Keep plausible circulation for a design brief; do not claim dimensions inferred from a photograph are construction measurements.

Save an editable scene checkpoint and a composition preview. Report the chosen units/scale, camera, imported assets, approximations, and any geometry limits that a shader cannot solve. Hand surface defects to [cycles-materials](../cycles-materials/SKILL.md) and photographic output to [light-and-render-interior](../light-and-render-interior/SKILL.md) only when those stages belong to the current task.

---
name: interior-design
description: Use when creating and rendering a complete interior from a reference image or design brief, or coordinating improvements across an existing room's layout, assets, materials, and lighting. Use a focused skill for a request limited to one of those areas.
---

# Interior design

Carry the user's interior task through an editable Blender scene and inspected Cycles images. Work from the current stage; an existing scene does not need to be rebuilt to improve it.

## Establish the brief and protect the starting point

Inspect the supplied images, existing scene, and prior results. Identify room function, must-match features, style, dimensions, camera/composition constraints, asset budget, and requested outputs. Distinguish observed facts from estimated dimensions and unseen architecture. Ask only for missing information that materially prevents progress; proceed with stated assumptions for ordinary visual choices.

Use the environment's existing Blender MCP connection and local workspace. Check the loaded file and unsaved work before scene changes. Save a recoverable checkpoint of an existing project before switching scenes through the runtime's safe loading workflow. Keep one persistent Blender process; opening another process or resetting the application can disconnect the agent from its work.

When the request is only a critique or discussion, return that assessment. When the request is to create, fix, or improve, continue through the authorized edits and rendered verification.

## Route the work

Read the relevant skill at the stage where it is needed. These are capabilities for the current agent, not instructions to spawn an agent for every stage.

| Stage | Skill | Evidence needed to move forward |
| --- | --- | --- |
| Room, composition, and assembly | [build-interior-scene](../build-interior-scene/SKILL.md) | A blockout matches the dominant proportions, framing, and object relationships. |
| Existing asset selection | [find-3d-models](../find-3d-models/SKILL.md) | The chosen source, access, dependencies, and fit are understood; downloaded assets have provenance. |
| Surface appearance | [cycles-materials](../cycles-materials/SKILL.md) | The intended materials and mapping work in the scene, with required textures readable. |
| Photographic lighting and output | [light-and-render-interior](../light-and-render-interior/SKILL.md) | A completed, readable image corresponds to the intended scene, camera, and render settings. |
| Diagnosis and refinement | [review-interior-render](../review-interior-render/SKILL.md) | The highest-impact defects have evidence, targeted corrections, and comparison renders. |

For reconstruction, settle the room proportions and camera before detailed props. For a design brief, establish a coherent layout and visual direction before decoration. Use simple geometry for early massing and suitable authored assets for complex hero objects. Spend detail where it affects the delivered view.

Keep a short local progress record containing the current scene/checkpoint, reference paths, camera and estimated scale, asset sources, last completed image, and next unresolved issue. This lets work resume without repeating earlier passes. Discover output paths from the workspace rather than hard-coding a particular machine or fixture.

## Refine with controlled comparisons

Use a modest preview to identify the largest remaining mismatch. Change a small related set of causes, preserve the previous pass, and inspect the next render. Keep approved composition and lighting stable during material comparisons. Separate a renderer's technical completion from visual improvement.

Complete material and lighting work that is possible with the available assets. When an asset cannot provide the requested silhouette or detail, report the limitation and use the user's accepted substitution; do not repeatedly revisit a rejected purchase or account requirement.

## Deliver

Deliver the native `.blend`, final image, useful before/after image links, and portable texture/asset dependencies with provenance. A viewer export is optional and does not replace the native master. State approximations and unresolved visual limitations. Only call an image rendered after the job completes and its output has been inspected; if a runtime failure prevents that, identify the last valid checkpoint and remaining action.

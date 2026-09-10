# Interior Design

A portable Codex plugin for creating and refining Blender interiors with native Cycles. The existing plugin identifier and folder remain `interior-desing`.

## Skills

| Skill | Use it for |
| --- | --- |
| [interior-design](skills/interior-design/SKILL.md) | A complete reference-to-render or design-brief workflow, including iteration and delivery. |
| [build-interior-scene](skills/build-interior-scene/SKILL.md) | Room geometry, camera matching, furniture placement, and asset integration. |
| [find-3d-models](skills/find-3d-models/SKILL.md) | Model discovery, comparison, verified downloads, and provenance. |
| [cycles-materials](skills/cycles-materials/SKILL.md) | Native materials, PBR mapping, physical texture scale, and surface repairs. |
| [light-and-render-interior](skills/light-and-render-interior/SKILL.md) | Photographic light balance, Cycles previews/finals, and render lifecycle checks. |
| [export-viewer-render](skills/export-viewer-render/SKILL.md) | High-resolution PNG export from an exact Three.js viewer camera, with scene-version verification and delivery confirmation. |
| [review-interior-render](skills/review-interior-render/SKILL.md) | Image-based diagnosis, comparisons, and targeted realism improvements. |

The complete workflow routes to these focused skills as needed. Each focused skill also supports an existing scene without restarting the whole process. Supporting references hold the conditional detail.

## Runtime contract

- Blender with Cycles and a working Blender MCP connection to one persistent process.
- Local filesystem access for scenes, scripts, downloads, and render status, plus an image-viewing tool for actual output inspection.
- Workspace instructions or runtime helpers that describe safe scene loading, saving, and asynchronous rendering. Skills inspect the available interface instead of assuming a fixture-specific API or path.
- Network access when acquiring models or textures. Public catalogs can be searched without the optional authenticated-provider credentials described in the model-finding reference.

Package the entire plugin directory, including its `.codex-plugin` manifest and skill references. It can be loaded by the sandbox's Codex plugin mechanism. The skills do not provision the sandbox, install Blender, register another MCP server, or include model weights, scenes, downloaded assets, or credentials. No V-Ray or Chaos dependency is required.

Scene edits and imports use Blender MCP. File operations and status inspection use local tools. Rendering uses the existing runtime workflow; a busy Blender process is handled as an active job until evidence establishes otherwise.

## Example requests

- “Recreate this reference room in Blender and deliver a Cycles render and editable scene.”
- “Make only the brown chair's leather less plastic; preserve the camera and lights.”
- “Render the current bedroom at the requested resolution and keep the previous pass.”
- “Compare these two renders and explain the largest regressions without editing the scene.”

Edited work should produce recoverable native scene checkpoints and inspected image outputs. The native `.blend` remains the editable master; a GLB viewer export is optional. Read-only reviews stay read-only, and unavailable rendering is reported as a verification limit.

## Testing this plugin

When asked to test the plugin, record its source revision, dirty state, and the skill/reference files actually read. If the source changes during the run, identify the instructions used and which changes remain untested.

Report technical delivery evidence and the final visual assessment separately. Link the inspected images and editable scene; give concrete dominant findings with their outcome and remaining constraints. Distinguish a plugin instruction gap from a task-helper bug, unsupported MCP command, or provider access failure. For each recovery, record what changed and what the next run demonstrated; changing two things together does not establish which one fixed the failure. Label instruction dry runs separately from live Blender execution, and limit conclusions to the tested revision and paths.

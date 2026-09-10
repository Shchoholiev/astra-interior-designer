---
name: light-and-render-interior
description: Use when lighting a Blender interior, adjusting its photographic exposure and color balance, or producing preview and final Cycles renders. Also applies to verifying render progress and outputs when Blender appears busy during rendering.
---

# Light and render an interior

Create photographic light relationships and deliver the actual rendered image. Keep a render-only request limited to output: preserve the user's approved lighting, camera, and color management unless a required change is explicitly part of the task.

For a high-resolution image export or a message containing "Viewer camera context
for this render", use [export-viewer-render](../export-viewer-render/SKILL.md) for
camera conversion, scene-version checks, and image delivery.

## Establish the render state

Inspect the open scene through Blender MCP: camera, render engine, visible collections, world and lights, output dimensions, resolution percentage, border/crop, exposure/view transform, sampling, denoising, and device configuration. Identify the previous image and save a scene checkpoint before making a lighting pass.

Use native Cycles. Select a backend supported by the actual runtime and confirm enabled devices as well as the scene's render device. A saved GPU flag alone does not establish GPU execution. If required hardware is unavailable, report that limitation; use CPU only when compatible with the user's time and hardware constraints. Read [render lifecycle](references/render-lifecycle.md) before submitting a job.

## Shape the light when lighting is in scope

Read [photographic lighting](references/photographic-lighting.md). Establish the principal source, supporting ambient contribution, and practical fixtures. Evaluate shadows and reflections as well as brightness. Keep enough direction and contrast for surfaces to read as solid objects.

Use a modest preview to judge the balance between exterior/daylight, warm fixtures, and indirect light. Correct source placement, size, and relative contribution before increasing every light or brightening all material colors. Adjust exposure and color management deliberately, preserving them for subsequent material comparisons.

Retain the established composition. Camera focus or depth of field should support the requested image, not hide unresolved detail. If a window, light opening, or fixture has incorrect geometry, report the dependency rather than compensating with unexplained fill lights.

## Preview, then finalize

Choose preview resolution and sampling to resolve the current question. A material seam needs a useful crop at sufficient pixel density; a lighting balance needs the full frame. For final output, inspect residual noise and denoising artifacts before raising the sample ceiling. Sampling settings are scene-dependent, not a fixed preset copied from a prior room.

Use the runtime's existing asynchronous render helper when available. Inspect its arguments and side effects first: a fixture preset can silently replace the current camera, exposure, or output settings. Keep one active render per Blender process, assign a unique output/job name, and track status through file tools while Blender is busy.

After completion, decode and inspect the output at full frame and relevant detail scale. Confirm camera, dimensions, border/crop, file format, color transform, and scene version. A file from an older job is not evidence for the current render.

## Deliver the checked output

Save the corresponding editable `.blend` with portable dependencies after the job is idle. Preserve the prior scene and image alongside the new pass. Return the image and scene paths, render engine/backend actually verified, elapsed time when measured, and any unresolved noise or visual issue. Distinguish render completion from a claim that the design improved.

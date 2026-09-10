# Render lifecycle and evidence

Use the environment's existing render service/helper through Blender MCP. Discover its API and output paths from current workspace instructions or local code. This skill does not install or start Blender, a display server, or an alternate renderer.

## Before submission

Record the current scene/checkpoint, camera, frame, output path, dimensions and percentage, crop/border, view transform/exposure, sampling, time limit, denoiser, and selected Cycles backend/devices. Choose a new job/output name so a failed rerun cannot be mistaken for an old successful file.

Inspect helper defaults. A method named `queue_render` can also apply fixture settings. Disable that behavior through its documented interface for a different room; do not assume every helper accepts the same flags. Read back the effective settings after configuration and before rendering.

GPU setup requires a supported backend, enabled devices in Cycles preferences, and a scene configured for GPU rendering. Use runtime or render evidence before reporting the actual device used; distinguish configuration from measured execution. [Blender GPU rendering](https://docs.blender.org/manual/sv/latest/render/cycles/gpu_rendering.html)

## Track the job

Map the actual helper's states to this distinction; do not invent status files or require these exact state names when the runtime uses others:

| State | Meaning and next action |
| --- | --- |
| Queued | Submission accepted; wait for execution. |
| Rendering | Work is active; inspect external status/logs at a bounded cadence. |
| Image written | Output may still need denoising, postprocessing, or validation. |
| Completed | Confirm the current job's final file can be decoded, then inspect the image. |
| Failed/cancelled | Preserve the previous good output and report the job error or cancellation. |

An MCP timeout while an external status record shows progress is not proof of a crash. Do not submit another render, reload the scene, edit it, or kill Blender while its job is active. Use file/log tools for progress and keep the user informed without busy polling. If progress stops, inspect available process and error evidence before deciding how to recover; a stale timestamp alone is not a diagnosis.

When a job fails, correct the demonstrated cause and retry within the task's time/resource constraints. Do not loop indefinitely on the same failure or silently reset the scene. Use the runtime's documented cancellation path when cancellation is requested.

## Sampling and completion

Adaptive sampling concentrates work on noisy pixels; a lower noise threshold can require more time. A time limit can end rendering before the desired noise level is reached. Inspect the resulting image rather than equating a sample count or time cap with quality. [Blender sampling](https://docs.blender.org/manual/de/latest/render/cycles/render_settings/sampling.html)

Use a supported denoiser with suitable auxiliary passes when available. Inspect fabric, leaf edges, reflections, and fine textures for residual noise or smearing. Do not repeatedly increase samples to repair UV seams, geometry errors, or flat illumination.

Verify the job identity, successful terminal state, readable pixels, output dimensions, and expected image content. Report measured elapsed time only when the runtime provides a valid start/end interval. Save or update the native master only after rendering is idle, retaining the previous checkpoint and avoiding a GLB round trip. Keep a compact per-pass record beside the output so another turn can identify exactly what was rendered.

---
name: export-viewer-render
description: Use when the user requests a high-resolution render or image export of the current interior, especially a message containing "Viewer camera context for this render", a scene version, Three.js world position and quaternion, vertical field of view, and aspect ratio. Render the supplied viewpoint and deliver the PNG.
---

# Export the viewer's render

Produce a Cycles image of the existing scene from the supplied viewer camera.
Preserve geometry, materials, lighting, and color management. Camera context is
an exact projection contract; do not replace it with a similar-looking camera,
auto-frame the room, level the horizon, or improve the composition.

If no viewer context is supplied, use the approved scene camera and current native
checkpoint, skip the viewer conversion steps below, and continue with rendering
and delivery. Do not invent viewer coordinates or request them unnecessarily.

## Establish the scene and camera

1. Inspect the live Blender process through MCP and the runtime's render helper.
   If it is rendering, follow [render lifecycle](../light-and-render-interior/references/render-lifecycle.md)
   before submitting another job. Record the native checkpoint and current frame.
2. Parse the supplied context with [viewer_camera.py](scripts/viewer_camera.py).
   It expects world position, quaternion in **x, y, z, w** order, effective vertical
   FOV in degrees (zoom already included), width/height aspect, and scene version.
   A camera-context message invokes this skill without requiring its explicit name.
3. Verify the requested scene version against the GLB actually shown in the viewer.
   The helper supports SHA-256 of that GLB's bytes. Establish that the current
   native scene is the corresponding master/export checkpoint; matching a GLB file
   alone does not prove an independently edited native scene matches it. For a
   stale version, use its matching checkpoint if available, or report the mismatch
   and obtain refreshed context. Do not overwrite the master by importing a GLB
   merely to fix a version mismatch. Resolve a different hash scheme explicitly.
4. Use the established viewer/export transform. This application's viewer keeps
   the GLB's original origin and scale. For a standard Y-up GLB exported from the
   unchanged Blender world, the inverse basis is `(x, y, z) -> (x, -z, y)`.
   Confirm exporter axes and any unit scaling from the export record. The helper
   accepts an explicit matrix for other pipelines; do not infer scaling from the
   model's bounding box. Read [camera contract](references/camera-contract.md)
   for the conversion, supported projection, and frontend requirements.

## Configure the export

Choose dimensions from the requested resolution, retaining the supplied aspect.
Without a specified size, default to 2K: a 2048-pixel long edge, rounding the other
dimension to the nearest pixel. A conflicting exact width/height and aspect needs resolution
before rendering; do not crop or stretch to satisfy both. The helper permits only
the unavoidable half-pixel rounding discrepancy.

Through Blender MCP, import the helper from this skill's actual directory:

```python
import importlib.util
spec = importlib.util.spec_from_file_location("viewer_camera", SCRIPT_PATH)
viewer_camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer_camera)
context = viewer_camera.parse_context(USER_CAMERA_MESSAGE)
evidence = viewer_camera.configure_camera(
    bpy.context.scene, context,
    glb_path=DISPLAYED_GLB_PATH,
    width=2048, height=1152,  # 2K example for a 16:9 viewer; preserve the actual aspect
)
```

`SCRIPT_PATH`, message, GLB path and dimensions must come from this task. Save the
returned camera evidence beside the unique render job. The helper creates a new,
unparented camera and retains existing cameras. It uses vertical sensor fit, zero
shift, square pixels, 100% resolution, and no border crop. Preserve supplied roll.
It does not change the scene's surfaces, lights, Cycles quality, or view transform.

Check the evaluated camera and render settings immediately before submission.
Timeline camera markers, stereo, sequencer output, compositor crop/transform nodes,
or a helper's presets must not replace the specified projection. Keep a recovery
checkpoint when changing output settings.

## Render, inspect, and deliver

Use the runtime's asynchronous native Cycles workflow and one active job per
Blender process. Preserve the validated camera and dimensions when configuring
samples/denoising. Render to a unique working PNG under the workspace's `renders/`
directory. A preview must use the same projection and aspect; it is not the final
high-resolution export. Follow the render lifecycle reference for terminal status,
safe progress monitoring, and idle-time decoding; do not add `render_stats` callbacks.

After completion, decode the new image, check its full dimensions, and inspect
the full frame plus relevant detail. Compare framing with the supplied viewer
image when available; otherwise verify the pose/projection numerically and state
that no browser screenshot comparison was possible. High resolution alone does not
establish acceptable noise or detail. A failed render keeps the previous export.

For the backend runtime, after visual acceptance use
[deliver_png.py](scripts/deliver_png.py) to atomically promote the PNG to
`/workspace/render.png`. The supervisor uploads it. Poll the existing
`/run/astra-exports/render-upload.json` at bounded intervals and compare **session
ID, object key, and SHA-256** using `check_receipt`. Stop on cancellation or the
runtime's delivery deadline; never treat an old receipt as the current upload.
The client gets the real download from `GET /sessions/{session_id}` through
`render_url`, `render_url_expires_at`, and `render_sha256`. Do not fabricate a URL
or use an S3 object key as a browser link. If upload is unconfirmed, return the
local result with delivery explicitly pending/failed.

In local Blender without that supervisor, deliver a clickable absolute PNG path
and inline image after inspection. Label it local delivery; do not create a fake
supervisor receipt. Return image dimensions, scene version, camera-match evidence,
and any visual or delivery limitation. Retain the native checkpoint and evidence.

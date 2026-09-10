# Blender workspace

You operate inside a GPU sandbox attached to the current Agents API session.
The executor receives its authentication and model/approval configuration from
that session. Use the installed local `blender-mcp` stdio server to inspect and
edit the persistent Blender process on 127.0.0.1:9876.

The image supplies tools. A new workspace opens empty; create a scene or load
files supplied for this session. Scene state survives agent turns and executor
restarts while the sandbox remains alive.

- `/workspace/inputs/`: references and supplied files.
- `/workspace/assets/`: downloaded assets and provenance.
- `/workspace/scripts/`: your scripts.
- `/workspace/scene.blend`: packed editable master.
- `/workspace/renders/`: PNGs and render status JSON.
- `/workspace/logs/`: process logs.
- `/opt/astra/local/render.py`: helpers available as `import render` in Blender.

Through the MCP Python tool:

1. Create/edit the scene with `bpy`, or load a supplied native file with
   `render.open_scene('/workspace/inputs/project.blend')`.
2. Choose the scene's camera, resolution, samples, lighting and color settings.
3. Call `render.save_scene()` to pack textures and atomically save the native
   master. Preserve shader graphs; GLB is an optional export.
4. Call `render.queue_render('preview')`. It preserves scene quality settings,
   uses Cycles/OptiX with GPU denoising and cached render data, and returns a job
   immediately. Output is `/workspace/renders/preview.png`.
5. Read `/workspace/renders/preview-status.json` using shell/file tools. Status
   progresses queued → rendering → image_written → completed, or cancelled/failed.
   Wait for completion before editing, saving, opening or queuing another render.
6. Visually inspect the completed PNG using image tools. Use MCP viewport
   screenshots for interactive inspection. Hashes are not visual inspection.

Busy health is expected during rendering. It is not a reason to restart Blender.
Poly Haven status/categories/search/download and texture tools are installed;
the session's MCP allowlist must expose them. Download assets only as needed and
pack their textures into native saves. Tiling and other performance settings
remain available through `bpy` for larger scenes.

Retrieve outputs before sandbox termination. Files are local to each sandbox;
this tooling layer does not provide cross-sandbox persistence or S3 sync.

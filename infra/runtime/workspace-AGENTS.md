
## Backend storage integration

This backend runtime extends the standalone tooling with S3 synchronization.
`/workspace/inputs/` is read-only and receives session uploads automatically.
Keep edits, downloaded assets and working files outside that directory.

Save the editable native master with `render.save_scene()`. To update the
frontend's scene, also export a self-contained GLB to `/workspace/scene.glb`.
The supervisor publishes that GLB to the session's storage and restores it in
replacement sandboxes. Native `.blend` files stay local. Executor reconnect
preserves the live Blender process and its files.

## Render image delivery

For a requested high-resolution image export, render to a working file under
`/workspace/renders/`. Wait for rendering to finish, inspect the actual image,
then atomically replace `/workspace/render.png` with the accepted PNG. Do not
render directly into this delivery path or publish intermediate previews there.
Preserve the requested camera, aspect ratio, and pixel dimensions.

The supervisor validates and uploads that PNG to this session's `render.png`
object in S3. Before reporting delivery complete, compare the file's SHA-256
with `sha256` in `/run/astra-exports/render-upload.json`. This read-only receipt
contains `session_id`, `object_key`, `sha256`, and `uploaded_at`; it is written
only after a successful upload. An absent receipt or a different hash means the
current image is not yet confirmed delivered. Preserve the file while uploads
retry and report a pending or failed delivery truthfully if confirmation never
arrives. Do not invent a URL or treat a local file path as a browser download.

The client obtains `render_url`, `render_url_expires_at`, and `render_sha256`
from `GET /sessions/{session_id}`. Only the latest exported image is retained;
working PNGs and the local receipt are not restored in replacement sandboxes.

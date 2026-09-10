# Render this view

The viewer button appends one ordinary user message to the active chat through the existing assistant-ui runtime and `/sessions/{id}/message` SSE flow. No new endpoint or render job table is required. The full camera context is persisted as message text; the UI collapses it under “Camera and scene details”. The button is unavailable without a loaded scene or while a turn is running.

At click time the UI captures the world position, world quaternion (x,y,z,w), effective vertical FOV (including zoom), aspect, clipping planes, projection matrix, and loaded scene's world transform. It requests PNG output with a 4096-pixel longest edge; the other dimension is rounded to whole pixels. The pose is a snapshot and does not follow later navigation.

## Blender interpretation

Matrices are column-major. Let `V` be `viewerWorldFromGltfColumnMajor` and `C` be `gltfFromBlenderColumnMajor`. Reconstruct the camera world matrix `W` from its position and quaternion. For the original Blender scene, use `inverse(C) * inverse(V) * W`. The standard exporter maps Blender `(x,y,z)` to glTF `(x,z,-y)`. Both camera-local conventions use -Z forward and +Y up. An importer may already apply the basis conversion; do not apply it twice.

Set a perspective camera with the supplied effective vertical FOV and aspect, square pixels, no lens shift or render border/crop. Preserve the existing geometry, materials, and lighting. Render separately from the editable master and GLB and return the image using the agent's existing image-delivery workflow. This UI change does not add or replace that delivery workflow.

## Scene identity

Signed URL query parameters are excluded from chat. `scene.asset` identifies the storage object; `scene.fingerprint` identifies the glTF content already loaded in the browser. It is **not** a hash of the original GLB file bytes or an immutable S3 version.

Fingerprint format: `gltf-content-sha256:<hex>`. Hash UTF-8 `JSON.stringify(parser.json)` followed by each loaded glTF buffer in index order. Prefix every part with its 4-byte little-endian byte length. All parts are hashed together with SHA-256. This avoids fetching a potentially overwritten object just to identify an older scene still displayed in the viewer. For a self-contained GLB, embedded images are included in its buffer content.

`immutableVersion` is currently null because the API does not return an immutable object version. The agent must not silently substitute a newer scene. Strong version enforcement requires backend version IDs or immutable artifacts; this message contract alone cannot guarantee retention of old scenes.

## Tests

From `web`, run `node --experimental-strip-types --test tests/render-view.test.mjs`, `npm run lint`, and `npx tsc --noEmit --incremental false`.

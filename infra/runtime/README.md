# Production sandbox runtime

`image.py` extends the tested tooling image
`im-ELY2dohC6fxZVS7MuAnm3x` and publishes `astra-blender:v5`. The base contains
Blender 5.2.1, Blender MCP 1.9.1, Codex CLI 0.153.4, Xvfb and the render/native-save
helpers and Pillow 12.1.1 from `infra/modal_local/`. This layer adds boto3 1.43.91 and the existing
S3/executor supervisor, plus the complete `plugins/interior-desing` plugin at
`/opt/astra/plugins/interior-desing`. New agent sessions expose that directory
through `environment.capability_directories`; the manifest, six skills, and their
references are baked into the image with `copy=True`. Plugin updates require a
new image build. No scene, texture or model is bundled. No packages install at startup.

Build from the repository root with the environment containing Modal 1.5.5:

```sh
.venv-modal/bin/python infra/runtime/image.py
```

This requires access to the base image in Modal workspace `serhii-9119` and builds
the candidate without naming it. It does not launch a sandbox. For integration
validation, keep the built object and pass it to `modal.Sandbox.create`:

```python
import modal
from infra.runtime.image import production_image

app = modal.App.lookup("astra-interior-designer-blender", create_if_missing=True)
image = production_image().build(app)
# Run the live session, storage, busy-health and reconnect checks using image.
# After they pass, publish this exact built image:
image.publish("astra-blender:v5")
```

`python infra/runtime/image.py --publish` performs the build and publication in
one command. Use it only after the same source has passed integration validation.
Keep future runtime changes under a new named version.

Each sandbox needs these environment variables:

| Variable | Source |
|---|---|
| `SESSION_ID` | OpenAI session identifier. |
| `ENVIRONMENT_ID` | That session's self-hosted environment identifier. |
| `AGENTS_REMOTE_URL` | The Agents API HTTPS remote endpoint. |
| `CODEX_API_KEY` | Restricted executor credential from a runtime secret. |
| `S3_BUCKET`, `S3_PREFIX` | Session bucket and exactly `sandboxes/{SESSION_ID}/`. |
| `AWS_REGION` | Bucket region. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Temporary credentials restricted to this session's storage. |

The backend application key and database credentials must stay outside the
sandbox. The runtime passes the executor key to `codex exec-server` through its
environment. Blender and Xvfb do not receive the executor or AWS credentials.
S3 uses explicit temporary credentials; no role or local profile fallback occurs.
Required S3 permissions are listing this session's `inputs/`, exact `scene.glb`
and `render.png` prefixes, reading its inputs, scene and render, and writing only
its `scene.glb` and `render.png` exports. Both the underlying sandbox role and
the STS session policy must allow these objects. Restore
uses `ListObjectsV2` with the exact scene prefix and requires an exact key match;
an empty listing means there is no persisted scene. It does not rely on `HEAD`
returning 404 under a prefix-constrained policy. The backend caps sandbox
lifetime before these credentials expire. No S3 filesystem mount is used.
The root supervisor downloads this session's inputs into `/workspace/inputs`.
Blender, Xvfb, and the executor run as `astra-agent` (UID/GID 10001). Input
directories belong to root with mode `0755`; downloaded files have mode `0444`.
The root-owned workspace uses the sticky bit so the agent can create working
files and scene exports without replacing the inputs directory. The supervisor
retains the S3 credentials; child processes do not receive them.

The backend command contract is:

```text
python /opt/astra/runtime.py start
python /opt/astra/runtime.py health
python /opt/astra/runtime.py reconnect-executor
python /opt/astra/runtime.py sync-inputs
```

`start` downloads inputs and restores the last complete GLB, starts Xvfb and persistent
Blender, executes a real scene query, then starts the executor. Blender reopens a
local native master if present, otherwise imports the restored GLB or starts empty.
The shared render helpers select OptiX GPU devices, GPU denoising, persistent data
and eight Blender threads. Native `.blend` files can be saved/reopened locally;
S3 persists the frontend's `scene.glb` export and the latest delivered `render.png`.
The PNG remains available through the backend after compute stops, but is not
restored into replacement sandboxes.
The MCP add-on and scene probes use loopback. The supervisor control socket is
local to `/run/astra`, with mode `0600`.

`health` prints JSON and returns zero only after a successful Blender scene query
with a running executor. The bootstrap records when a Blender command is executing.
Queued and active asynchronous renders also keep health busy after the MCP call
returns. Health during that work returns `blender_state: "busy"`, `blender_busy: true`,
`blender_ready: false`, and exit 2. An alive process that does not answer but has
no command marker is `unresponsive`; an exited Blender process is `dead`. Failed
health is never a restart instruction. The backend treats a nonzero probe as
unknown and retains the workspace. An unexpected essential process exit causes
the supervisor to clean up its process groups and exit.

`reconnect-executor` serializes requests within the supervisor and replaces only
the executor process group. It preserves Blender, Xvfb, the environment ID, and
local files. Its success means the replacement process launched; the backend
must separately observe the OpenAI environment connection before submitting work.

Every two seconds, the supervisor downloads new or changed inputs using
conditional S3 reads and atomic local replacements, then checks scene and PNG exports.
`sync-inputs` performs the same serialized input download on demand. The backend
waits for it before submitting a message with attachments; the upload endpoint and
its presigned PUT contract are unchanged. Working files belong elsewhere under
`/workspace`. The supervisor publishes `scene.glb` only
after two unchanged file observations and successful validation of a complete,
self-contained GLB. Uploads read a separate stable snapshot and set
`Content-Type: model/gltf-binary`. Identical scene contents are not uploaded again.
An accepted image is promoted atomically from `/workspace/renders/` to
`/workspace/render.png` by the agent. The supervisor applies the same two-observation
and stable-snapshot checks, verifies PNG integrity and pixel decoding with Pillow,
then uploads with `Content-Type: image/png`, `Cache-Control: no-cache`, and SHA-256
in S3 user metadata. Incomplete, corrupt, or non-PNG files do not replace the
previous delivered image. Identical PNG contents are not uploaded again.

After a successful upload, the supervisor atomically writes
`/run/astra-exports/render-upload.json` containing `session_id`, `object_key`,
`sha256`, and UTC `uploaded_at`. The directory is root-owned `0755` and the receipt
is root-owned `0444`, readable by the agent. The agent must compare its accepted
file's hash with the receipt before claiming delivery. A failed receipt write is
retried without reuploading the same bytes. Previews stay local and never receive
delivery receipts. No new database record or render job endpoint is involved.

Input, scene, and render failures are retried independently and exposed as
`storage_error` in health and provider logs. Graceful shutdown attempts one final
upload of each export; hard termination cannot promise
an upload that has not already completed.

Local verification:

```sh
.venv/bin/python -m unittest discover -s tests -p test_runtime.py -v
.venv/bin/ruff check infra/runtime tests/test_runtime.py
```

The local suite uses simulated S3 and Blender boundaries, real local processes,
and local sockets. It verifies storage safety and supervisor behavior without
credentials or GPU compute. Live Agents API attachment and S3 transfer checks
remain required before production publication.

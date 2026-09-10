# RTX Blender sandbox tooling

A reusable Modal image with Blender 5.2.1 LTS, Blender MCP 1.9.1 and Codex 0.153.4
preinstalled. The supervisor keeps Blender and Xvfb alive alongside an
authenticated Agents API `codex exec-server`. Each new workspace starts empty;
scenes and assets are supplied or generated at runtime.

The image contains only software, runtime helpers and workflow instructions.
Its build inputs are an explicit allowlist under `infra/`; no project scene,
texture, model, reference image, generated render or fixture bundle is copied.
The official Blender archive checksum and installed software versions are
verified during the build. No package installation occurs during normal startup.

## Build and verify

Install host tools once, then authenticate Modal:

```sh
python3 -m venv .venv-modal
.venv-modal/bin/pip install -r infra/modal_local/requirements-host.txt
.venv-modal/bin/modal setup
```

Build the image and record its immutable ID:

```sh
.venv-modal/bin/python infra/modal_local/manage.py build --output /tmp/blender-image.json
```

Validate two independent copies using a procedural test scene created only
inside the temporary test sandboxes:

```sh
.venv-modal/bin/python infra/modal_local/manage.py verify --build \
  --output /tmp/blender-tooling-validation
```

Use a new output directory each time, or replace `--build` with
`--image-id im-YOUR_IMAGE`. Verification checks empty startup, real MCP calls,
GPU rendering, packed native save/reopen, render status, client restart and
workspace isolation, retrieves outputs, then terminates its test sandboxes.
Add `--check-assets` to also exercise Poly Haven search and a runtime download.
The default check needs no scene input or asset download.

`requirements.txt` pins direct dependencies and `requirements.lock` pins their
resolved versions. The image retains `/opt/astra/local/versions.json`, Python
and OS package snapshots, and a Node package snapshot. An authenticated Agents
API turn and executor reconnect are separate integration checks; the direct
MCP test does not claim to prove them.

## Attach an Agents API executor

The session owner supplies its environment ID, the exact session-specific
`environment.remote_url`, and a Modal secret containing the restricted
`CODEX_API_KEY`. Keep the broader application credential outside the sandbox.

```sh
.venv-modal/bin/python infra/modal_local/manage.py start \
  --image-id im-YOUR_IMAGE \
  --environment-id YOUR_ENVIRONMENT_ID \
  --remote-url YOUR_SESSION_ENVIRONMENT_REMOTE_URL \
  --executor-secret YOUR_MODAL_EXECUTOR_SECRET
```

A generic API base URL is not the executor attachment URL. Authentication is
passed at runtime. For a diagnostic sandbox, use `--blender-only` instead of
these three executor options.

The consuming backend can use these commands with `ENVIRONMENT_ID`,
`AGENTS_REMOTE_URL` and `CODEX_API_KEY` in the supervisor environment:

```text
python /opt/astra/local/boot.py start
python /opt/astra/local/boot.py health
python /opt/astra/local/boot.py reconnect-executor
```

The supervisor checks a real Blender scene query before starting the executor.
Blender/Xvfb do not inherit executor/OpenAI/Modal/AWS credential variables.
The backend owns API connection readiness; a process being alive is not proof
that the executor is connected. An executor exit leaves Blender and files intact
so it can reconnect to the existing session.

Configure Agents API's MCP server as the installed stdio command `blender-mcp`,
with `connection_origin="environment"`, cwd `/workspace`, and inherited variables
`BLENDER_HOST`, `BLENDER_PORT` and `DISABLE_TELEMETRY`. Expose the needed tools:

```text
get_scene_info, get_object_info, get_viewport_screenshot, execute_blender_code,
get_addon_status, get_polyhaven_status, get_polyhaven_categories,
search_polyhaven_assets, download_polyhaven_asset, set_texture
```

The optional CLI TOML is for Blender-only diagnostics. It is not installed as a
second MCP configuration in the authenticated executor mode.

## Create, render and retrieve

Upload inputs only when a session needs them:

```sh
.venv-modal/bin/python infra/modal_local/manage.py put sb-YOUR_SANDBOX project.blend /workspace/inputs/project.blend
.venv-modal/bin/python infra/modal_local/manage.py exec --pty sb-YOUR_SANDBOX -- bash
.venv-modal/bin/python infra/modal_local/manage.py health sb-YOUR_SANDBOX
```

In a Blender MCP Python call:

```python
import bpy, render

# Or create the scene directly with bpy.
render.open_scene("/workspace/inputs/project.blend")
# Inspect/edit and choose camera, resolution, samples and color settings.
render.save_scene()
render.queue_render("preview")
```

Read `/workspace/renders/preview-status.json` with ordinary file tools until
`status="completed"`, then inspect `/workspace/renders/preview.png`. The helper
preserves the scene's camera and quality settings, writes PNG, and validates the
image before reporting completion. `save_scene()` packs textures and atomically
replaces `/workspace/scene.blend`; `open_scene()` restores it without losing MCP.
An existing native master is reopened at startup; an unreadable file is an error.

Resources are one RTX PRO 6000, four reserved CPU cores and 16 GiB RAM. Cycles
uses OptiX, GPU denoising, persistent render data and eight Blender worker threads.
Modal permits CPU bursting. Camera/resolution/samples/color settings remain under
the scene's control; tiling can be adjusted through `bpy` for the workload.
A local benchmark found little benefit from raising the CPU reservation from
four to eight cores after GPU denoising/cache optimization; this is not a
performance guarantee for arbitrary scenes.

```sh
.venv-modal/bin/python infra/modal_local/manage.py get sb-YOUR_SANDBOX /workspace/renders/preview.png ./preview.png
.venv-modal/bin/python infra/modal_local/manage.py get sb-YOUR_SANDBOX /workspace/scene.blend ./scene.blend
.venv-modal/bin/python infra/modal_local/manage.py reconnect-executor sb-YOUR_SANDBOX
.venv-modal/bin/python infra/modal_local/manage.py stop sb-YOUR_SANDBOX
```

`put` replaces the explicitly selected remote file; `get` refuses to overwrite
an existing local file. Retrieve outputs before stopping. The hard lifetime is
at most one hour with no idle timeout. Files are sandbox-local; this standalone
layer does not add a Volume, S3 sync, or backend deployment.

After validation, publish an image under a fresh name if needed:

```sh
.venv-modal/bin/python infra/modal_local/manage.py publish \
  --image-id im-YOUR_IMAGE --name astra-blender:tooling-v1
```

The command protects the existing `astra-blender:v1` name.

The backend uses `astra-blender:v3`, built by `infra/runtime/image.py` on this
tested tooling image. That layer retains the backend's S3 synchronization and
unprivileged process contract. Its launch/health/reconnect/sync-inputs commands
remain under `/opt/astra/runtime.py`; see `../runtime/README.md`.

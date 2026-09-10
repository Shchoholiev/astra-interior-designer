# Agent API

| Endpoint | Contract | Sandbox / storage actions |
|---|---|---|
| `POST /sessions` | Create an Agents API session and return `session_id` immediately after persistence. | Assign storage prefix `sandboxes/{session_id}/` and start the sandbox in the background. Session status is `starting`, then `idle` when ready or `failed` if startup fails. |
| `GET /sessions` | Return the current user's sessions ordered by most recently updated. | Read session metadata from DynamoDB. Do not start compute or generate signed scene URLs. |
| `GET /sessions/{session_id}` | Return session status, sandbox status, paginated chat history, `scene_url` / `scene_url_expires_at`, and `render_url` / `render_url_expires_at` / `render_sha256`. URLs are presigned for 12 hours (`43,200` seconds). Each export's fields are `null` before its first upload. | Read session metadata and messages from DynamoDB. Inspect the existing sandbox and resolve `sandboxes/{session_id}/scene.glb` and `render.png` in S3; do not start compute. |
| `POST /sessions/{session_id}/message` | Accept `{message_id, text, attachment_keys?}` and stream native Agents API events over SSE. Use `message_id` as the idempotency key. Attachments reference objects under this session's `inputs/` prefix. | Wait for any background startup, then reuse the sandbox or start it if stopped. Send SSE startup progress while waiting for Blender/MCP and the executor before submitting input. |
| `POST /sessions/{session_id}/cancel` | Request cancellation of the active turn through the Agents API. | No sandbox shutdown. Preserve the chat, DB history, and S3 files. |
| `POST /sessions/{session_id}/files/upload-url` | Accept `{filename, content_type}`. Return a new `object_key`, presigned PUT `upload_url`, required headers, and expiry. | No sandbox needed. The browser uploads directly under `sandboxes/{session_id}/inputs/` in the shared bucket. |

# Sandbox service

| Contract | Responsibility |
|---|---|
| `start(session_id, environment_id, remote_url, bucket_name, storage_prefix) -> SandboxHandle` | Provision Modal `RTX-PRO-6000` compute from a prebuilt image containing Blender, its MCP integration, the S3 SDK, and `codex exec-server`. Pass the session's Agents API `remote_url` through unchanged, configure access to `storage_prefix` in the shared bucket, prepare local `/workspace`, launch Blender/MCP and the executor, and make MCP tools callable by the agent. Return `sandbox_id`. |
| `get(sandbox_id) -> SandboxState` | Report provider state and Blender/MCP health. Provider startup alone does not imply the agent can use the sandbox. |
| `sync_inputs(sandbox_id) -> None` | Wait for uploaded inputs to reach a running sandbox before submitting an attachment message. |
| `stop(sandbox_id) -> None` | Internal compute cleanup; safe to repeat if already stopped. Preserve the chat, DB history, and S3 files. |
| Session orchestration | Persist `session_id`, `environment_id`, `sandbox_id`, and `storage_prefix`. The shared bucket name is backend configuration. Own duplicate-start prevention, Agents API connection readiness, messaging, cancellation, and startup-failure cleanup. Browser disconnection does not cancel work or stop compute. |

# Chat persistence

DynamoDB on-demand, accessed by FastAPI. `session_id` is the Agents API session ID.

| Table | Partition key | Sort key | Stored data |
|---|---|---|---|
| `sessions` | `session_id` | None | Ownership, title, environment ID, sandbox ID, storage prefix, last known status, timestamps. |
| `messages` | `session_id` | `message_key` | One item per message/tool result: role/type, content, status, upstream item/turn IDs, attachment object keys. |

`message_key` combines a fixed-format UTC creation timestamp and a stable message/item ID. Reuse the same key for retries and updates. Query by `session_id` to read messages in timestamp order, with pagination.

Save user input before submission and completed agent/tool items as they arrive. Persistence continues after browser disconnection; reconcile missed output from retained Agents API items. File bytes stay in S3.

# S3 storage

| Contract | Responsibility |
|---|---|
| Storage | One private bucket. Files under `sandboxes/{session_id}/`; viewer scene at `scene.glb`, latest exported image at `render.png`. Store object keys as permanent references. |
| Modal | Download new inputs from S3 every two seconds into `/workspace/inputs/`, read-only to Blender and the agent. Confirm attachment downloads before submitting their message. Upload complete, self-contained `scene.glb` exports and accepted PNG exports through the S3 SDK. Working files remain local. |
| Frontend | Load `scene_url` in Three.js; use `render_url` to display or download the exported PNG and `render_sha256` to identify the latest image. Presigned downloads last 12 hours; signing credentials must cover that window. Upload through presigned PUT URLs. |
| Access | Credentials in backend/Modal secrets. Restrict access to the session's prefix; configure CORS for the frontend. |
| Persistence | Inputs and uploaded scene/image exports survive sandbox stops. The local working `.blend`, render previews, and other unsaved state do not. |

The image contract is one latest PNG per session, without export history. The agent
finishes and inspects a working render before atomically promoting it to
`/workspace/render.png`. After validation and upload, the supervisor writes
`/run/astra-exports/render-upload.json` with the uploaded SHA-256; the agent checks
it against the local file before claiming delivery. A failed or incomplete new
render leaves the previous uploaded image available.

`render_sha256` comes from S3 metadata recorded with the uploaded bytes, not a
live sandbox query. The URL points to the mutable latest-image key: a subsequent
export can change its contents during the URL's lifetime. Refetch session details
after an export and, if a download's hash differs, refetch and retry. The response
does not promise an immutable historical version. Missing objects return null;
permission failures or missing checksum metadata are storage errors.

# Workspace mapping

| Sandbox path | S3 location |
|---|---|
| `/workspace/inputs/` (read-only to the agent) | `sandboxes/{session_id}/inputs/` |
| `/workspace/scene.glb` | `sandboxes/{session_id}/scene.glb` |
| `/workspace/render.png` | `sandboxes/{session_id}/render.png` (latest accepted export) |
| `/workspace/renders/`, `/run/astra-exports/render-upload.json` | Local previews and upload receipt only. |
| Working `.blend`, scripts, and temporary files | Local only. |

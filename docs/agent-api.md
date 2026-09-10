# Agent API

| Endpoint | Contract | Sandbox / storage actions |
|---|---|---|
| `POST /sessions` | Create an Agents API session. Return `session_id`. | Assign storage prefix `sandboxes/{session_id}/` in the shared private bucket, persist the association, and start its sandbox. |
| `GET /sessions/{session_id}` | Return session status, sandbox status, paginated chat history, and a fresh presigned `scene_url` valid for 12 hours (`43,200` seconds), with `scene_url_expires_at`. `scene_url` is `null` before the first export. | Read session metadata and messages from DynamoDB. Inspect the existing sandbox and resolve `sandboxes/{session_id}/scene.glb` in S3; do not start compute. |
| `POST /sessions/{session_id}/message` | Accept `{message_id, text, attachment_keys?}` and stream native Agents API events over SSE. Use `message_id` as the idempotency key. Attachments reference objects under this session's `inputs/` prefix. | Reuse the sandbox or start it if stopped. Wait for Blender/MCP readiness and Agents API executor connection before submitting input. |
| `POST /sessions/{session_id}/cancel` | Request cancellation of the active turn through the Agents API. | No sandbox shutdown. Preserve the chat, DB history, and S3 files. |
| `POST /sessions/{session_id}/files/upload-url` | Accept `{filename, content_type}`. Return a new `object_key`, presigned PUT `upload_url`, required headers, and expiry. | No sandbox needed. The browser uploads directly under `sandboxes/{session_id}/inputs/` in the shared bucket. |

# Sandbox service

| Contract | Responsibility |
|---|---|
| `start(session_id, environment_id, bucket_name, storage_prefix) -> SandboxHandle` | Provision Modal `RTX-PRO-6000` compute from a prebuilt image containing Blender, its MCP integration, the S3 SDK, and `codex exec-server`. Configure access to `storage_prefix` in the shared bucket, prepare local `/workspace`, launch Blender/MCP and the executor, and make MCP tools callable by the agent. Return `sandbox_id`. |
| `get(sandbox_id) -> SandboxState` | Report provider state and Blender/MCP health. Provider startup alone does not imply the agent can use the sandbox. |
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
| Storage | One private bucket. Files under `sandboxes/{session_id}/`; viewer scene at `scene.glb`. Store object keys as permanent references. |
| Modal | Share only the input files folder and exported `scene.glb` with S3. Keep working Blender files, scripts, and temporary files local. Exports are self-contained GLBs. |
| Frontend | Load `scene_url` from the session endpoint in Three.js. Presigned downloads last 12 hours; signing credentials must cover that window. Upload through presigned PUT URLs. |
| Access | Credentials in backend/Modal secrets. Restrict access to the session's prefix; configure CORS for the frontend. |
| Persistence | Inputs and uploaded scene exports survive sandbox stops. The local working `.blend` and other unsaved state do not. |

# Workspace mapping

| Sandbox path | S3 location |
|---|---|
| `/workspace/inputs/` | `sandboxes/{session_id}/inputs/` |
| `/workspace/scene.glb` | `sandboxes/{session_id}/scene.glb` |
| Working `.blend`, scripts, and temporary files | Local only. |

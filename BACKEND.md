# Astra Interior Designer API

Python 3.12+, managed with uv. Run from the repository root:

```sh
uv sync
# Copy only if you do not already have a local .env.
cp -n .env.example .env
uv run fastapi dev
```

Fill in the required settings before starting. API docs are at
<http://127.0.0.1:8000/docs>. Every session endpoint requires
`Authorization: Bearer <APP_API_KEY>`; the demo uses one shared owner.

The endpoint and storage contracts are in [docs/agent-api.md](docs/agent-api.md).

```text
src/astra_interior_designer/
├── api/
│   ├── __init__.py
│   └── sessions.py
├── services/
│   ├── __init__.py
│   ├── sandbox.py
│   ├── sessions.py
│   └── storage.py
├── __init__.py
├── config.py
├── dependencies.py
└── main.py
```

## Configuration

Use the ignored `.env` locally. For deployment, set `AWS_SECRET_ID` to an AWS
Secrets Manager JSON secret and let the backend's IAM role read it at startup.
The supported secret fields are `OPENAI_API_KEY`, `APP_API_KEY`,
`S3_SIGNING_ACCESS_KEY_ID`, and `S3_SIGNING_SECRET_ACCESS_KEY`. Explicit settings,
environment variables, and local `.env` values take precedence over the secret.
Resource names and runtime commands stay in ordinary deployment configuration.

The provisioned resources are in `us-east-1`:

| Resource | Name |
|---|---|
| Session table | `astra-interior-designer-sessions` |
| Message table | `astra-interior-designer-messages` |
| Private files bucket | `astra-interior-designer-files-022104542793` |

Local AWS access uses profile `astra-interior-designer`. Deployment should use an
IAM role with access to these resources and the configured secret. Set
`SANDBOX_S3_ROLE_ARN` to a role the backend can assume; each sandbox receives
temporary credentials further restricted to its own inputs and scene object.
The sandbox lifetime is capped below those credentials' expiry.

Scene download URLs last 12 hours. Their signing credentials must cover the full
12 hours; a short-lived AWS login or runtime role is insufficient. The optional
`S3_SIGNING_*` pair selects a separate signer, whose permissions must cover the
session inputs and scene objects. Short-lived credentials can sign upload URLs,
whose lifetime is capped at 15 minutes and their remaining validity.

## Modal runtime

Configure a published image, launch/health/reconnect commands, and a named Modal
secret containing the restricted executor credential. The adapter provisions
`RTX-PRO-6000` compute and waits for both Blender health and an actual Agents API
executor connection. Reconnection must preserve the existing Blender process.

`POST /sessions` returns its saved session ID before sandbox startup finishes.
Startup runs in the background; `GET /sessions/{session_id}` exposes `starting`,
`idle`, or `failed`. The first message waits for startup through the existing SSE
progress stream. Startup failure preserves the session so its status remains visible.

The default `astra-blender:v4` image layers the existing S3/executor runtime onto
the tested Blender tooling image. Build and publish it with
`infra/runtime/image.py`; the standalone tooling image is its base. The backend
retains the `/opt/astra/runtime.py` start/health/reconnect/sync-inputs commands.
New workspaces contain no bundled scene or assets. Session uploads and persisted
GLB exports are restored at runtime; Blender uses the shared native-save and
asynchronous OptiX render helpers.

The image includes the complete Interior Design plugin at
`/opt/astra/plugins/interior-desing`. New sessions register that path in
`environment.capability_directories`, exposing its six skills and references to
the agent without copying or downloading them at startup.

## Frontend

Send `{message_id, text, attachment_keys?}` to the message endpoint using
`@microsoft/fetch-event-source`. Keep the same `message_id` when retrying the same
input, set `openWhenHidden: true`, and disable automatic retries initially.
The stream retains native Agents API event names, IDs, and JSON payloads. Read
persisted history with `GET /sessions/{session_id}` after reconnecting. Browser
disconnection does not cancel the turn; use the cancel endpoint explicitly.
Upstream items too large for DynamoDB retain their IDs and an explicit
`content_omitted` marker so they cannot block the rest of the chat.

Set `CORS_ORIGINS` for the backend and configure bucket CORS for the same frontend
origin with `GET`, `HEAD`, and `PUT` access. Upload directly using the returned
URL and required headers; load the session's `scene_url` with Three.js.

## Checks

```sh
uv run ruff check src
uv run ruff format --check src
```

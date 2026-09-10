"""The browser-facing session API."""

import asyncio
import hmac
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from astra_interior_designer.dependencies import Services

router = APIRouter(prefix="/sessions", tags=["sessions"])
bearer = HTTPBearer(auto_error=False)
SessionId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)


class CreatedSession(BaseModel):
    session_id: str


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    text: str = Field(min_length=1, max_length=32_000)
    attachment_keys: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message text cannot be blank")
        return value


class UploadFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)


class UploadURL(BaseModel):
    object_key: str
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    message_id: str
    role: str
    content: JsonValue
    status: str
    created_at: datetime
    item_id: str | None = None
    turn_id: str | None = None
    attachment_keys: tuple[str, ...] = ()


class Session(BaseModel):
    session_id: str
    title: str | None
    status: str
    sandbox_status: str
    messages: list[Message]
    next_cursor: str | None
    scene_url: str | None
    scene_url_expires_at: datetime | None


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_owner(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    expected = request.app.state.settings.app_api_key
    if expected is None or not expected.get_secret_value():
        raise HTTPException(503, "Configure APP_API_KEY before using the API")
    if credentials is None or not hmac.compare_digest(
        credentials.credentials, expected.get_secret_value()
    ):
        raise HTTPException(
            401, "Invalid API token", headers={"WWW-Authenticate": "Bearer"}
        )
    return "demo"


ServicesDependency = Annotated[Services, Depends(get_services)]
OwnerDependency = Annotated[str, Depends(get_owner)]


@router.post("", status_code=201, response_model=CreatedSession)
async def create_session(
    services: ServicesDependency,
    owner_id: OwnerDependency,
    body: CreateSession = Body(default_factory=CreateSession),
) -> CreatedSession:
    record = await services.sessions.create_session(owner_id=owner_id, title=body.title)
    return CreatedSession(session_id=record.session_id)


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: SessionId,
    services: ServicesDependency,
    owner_id: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> Session:
    record = await services.sessions.get_session(session_id, owner_id=owner_id)
    history = await services.storage.list_messages(
        session_id, limit=limit, cursor=cursor
    )
    sandbox_status = "missing"
    if record.sandbox_id:
        sandbox_status = (await services.sandbox.get(record.sandbox_id)).status
    scene = await services.files.scene_url(session_id)
    return Session(
        session_id=record.session_id,
        title=record.title,
        status=record.status,
        sandbox_status=sandbox_status,
        messages=[Message.model_validate(message) for message in history.messages],
        next_cursor=history.next_cursor,
        scene_url=scene.url if scene else None,
        scene_url_expires_at=scene.expires_at if scene else None,
    )


@router.post("/{session_id}/message", response_class=StreamingResponse)
async def send_message(
    session_id: SessionId,
    body: SendMessage,
    services: ServicesDependency,
    owner_id: OwnerDependency,
) -> StreamingResponse:
    async def stream() -> AsyncIterator[bytes]:
        # Open the response before sandbox readiness work. Without an early
        # chunk, CloudFront can reach its origin response timeout before Modal
        # has connected the executor, so the browser never receives SSE.
        yield b": connected\n\n"
        preparing = asyncio.create_task(
            services.sessions.stream_message(
                session_id,
                owner_id=owner_id,
                message_id=body.message_id,
                text=body.text,
                attachment_keys=body.attachment_keys,
            )
        )
        try:
            while not preparing.done():
                await asyncio.wait({preparing}, timeout=10)
                if not preparing.done():
                    yield b": preparing\n\n"
            events = await preparing
            async with aclosing(events):
                async for event in events:
                    yield event
        except asyncio.CancelledError:
            preparing.cancel()
            raise
        except Exception:
            payload = json.dumps(
                {"detail": "Unable to start or continue the generation"},
                separators=(",", ":"),
            )
            yield f"event: astra.error\ndata: {payload}\n\n".encode()
        finally:
            if not preparing.done():
                preparing.cancel()
            await asyncio.gather(preparing, return_exceptions=True)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/cancel", status_code=204)
async def cancel_session(
    session_id: SessionId, services: ServicesDependency, owner_id: OwnerDependency
) -> Response:
    await services.sessions.cancel(session_id, owner_id=owner_id)
    return Response(status_code=204)


@router.post("/{session_id}/files/upload-url", response_model=UploadURL)
async def upload_url(
    session_id: SessionId,
    body: UploadFile,
    services: ServicesDependency,
    owner_id: OwnerDependency,
) -> UploadURL:
    await services.sessions.get_session(session_id, owner_id=owner_id)
    upload = await services.files.upload_url(
        session_id, body.filename, body.content_type
    )
    return UploadURL(
        object_key=upload.object_key,
        upload_url=upload.url,
        headers=upload.headers,
        expires_at=upload.expires_at,
    )

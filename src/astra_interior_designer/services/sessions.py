"""Session lifecycle and durable delivery around the pinned Agents API SDK."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import uuid4

from agent_api_sdk import AgentAPIError, AgentAPISDK
from agent_api_sdk._session import AsyncAgentSession
from agent_api_sdk._types import McpToolParam, SessionEvent

from astra_interior_designer.services.storage import (
    MessageRecord,
    RecordTooLarge,
    SessionRecord,
)

log = logging.getLogger(__name__)
_TERMINAL_MESSAGES = {"completed", "failed", "cancelled"}
_TURN_END = {
    "session.turn.completed": "completed",
    "session.turn.failed": "failed",
    "session.turn.cancelled": "cancelled",
}

_BLENDER_TOOL: McpToolParam = {
    "type": "mcp",
    "server_label": "blender",
    "connection_origin": "environment",
    "required": True,
    "transport": {
        "type": "stdio",
        "command": "blender-mcp",
        "args": [],
        "cwd": "/workspace",
        "env_vars": ["BLENDER_HOST", "BLENDER_PORT", "DISABLE_TELEMETRY"],
    },
    "allowed_tools": [
        "get_scene_info",
        "get_object_info",
        "get_viewport_screenshot",
        "execute_blender_code",
        "get_addon_status",
    ],
}


class SessionNotFound(Exception):
    """The session does not exist or belongs to another owner."""


class SessionConflict(Exception):
    """A message ID was reused, or another process owns the active turn."""


class SessionUnavailable(Exception):
    """The runtime or its upstream connection is not ready."""

    def __init__(self, message: str, *, sandbox_id: str | None = None):
        super().__init__(message)
        self.sandbox_id = sandbox_id


@dataclass
class _Lease:
    token: str
    lost: bool = False
    heartbeat: asyncio.Task | None = None
    item_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _LiveSession:
    session: AsyncAgentSession
    opened: asyncio.Event = field(default_factory=asyncio.Event)
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    task: asyncio.Task | None = None
    recovery: asyncio.Task | None = None
    message: MessageRecord | None = None
    terminal: str | None = None
    retry_delay: float = 0
    child_turns: set[str] = field(default_factory=set)
    error: Exception | None = None
    finishing: asyncio.Lock = field(default_factory=asyncio.Lock)


class _Subscription:
    def __init__(self, live: _LiveSession, capacity: int):
        self.live = live
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(capacity)
        self.closed = False
        live.subscribers.add(self.queue)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        try:
            chunk = await asyncio.wait_for(self.queue.get(), timeout=15)
        except TimeoutError:
            return b": keep-alive\n\n"
        except asyncio.CancelledError:
            await self.aclose()
            raise
        if chunk is None:
            await self.aclose()
            raise StopAsyncIteration
        return chunk

    async def aclose(self):
        self.closed = True
        self.live.subscribers.discard(self.queue)


def encode_sse(event: SessionEvent) -> bytes:
    """Preserve the SDK's native event name, SSE ID, and original JSON payload."""
    lines = []
    if event.event_name is not None:
        lines.append(f"event: {event.event_name}")
    if event.sse_event_id is not None:
        lines.append(f"id: {event.sse_event_id}")
    lines.append("data: " + json.dumps(event.data, separators=(",", ":")))
    return ("\n".join(lines) + "\n\n").encode()


async def _empty_stream() -> AsyncIterator[bytes]:
    if False:
        yield b""


class SessionService:
    def __init__(
        self,
        store,
        files,
        sandbox,
        sdk: AgentAPISDK,
        *,
        bucket_name: str,
        model: str = "gpt-6-astra",
        instructions: str = (
            "You are an interior design assistant. Use Blender and its installed MCP "
            "tools to edit scenes. Input files are in /workspace/inputs. Export a "
            "self-contained GLB to /workspace/scene.glb for the browser viewer."
        ),
        readiness_timeout: float = 120,
        poll_interval: float = 1,
        lease_seconds: int = 180,
        subscriber_queue_size: int = 128,
        shutdown_timeout: float = 10,
    ):
        self.store = store
        self.files = files
        self.sandbox = sandbox
        self.sdk = sdk
        self.bucket_name = bucket_name
        self.model = model
        self.instructions = instructions
        self.readiness_timeout = readiness_timeout
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.subscriber_queue_size = subscriber_queue_size
        self.shutdown_timeout = shutdown_timeout
        self._live: dict[str, _LiveSession] = {}
        self._leases: dict[str, _Lease] = {}
        self._closed = False

    async def _owned(self, session_id: str, owner_id: str) -> SessionRecord:
        record = await self.store.get_session(session_id)
        if record is None or record.owner_id != owner_id:
            raise SessionNotFound("Session not found")
        return record

    async def create_session(
        self, *, owner_id: str, title: str | None = None
    ) -> SessionRecord:
        if self._closed:
            raise SessionUnavailable("Backend is shutting down")
        session = await self.sdk.sessions.create(
            agent={
                "model": self.model,
                "instructions": self.instructions,
                "tools": [_BLENDER_TOOL],
            },
            environment={"type": "self_hosted", "workspace_directory": "/workspace"},
        )
        sandbox_id = None
        saved = False
        try:
            environment_id = session.info.environment.environment_id
            record = SessionRecord(
                session_id=session.id,
                environment_id=environment_id,
                storage_prefix=f"sandboxes/{session.id}/",
                remote_url=session.info.environment.remote_url,
                owner_id=owner_id,
                title=title,
            )
            await self.store.create_session(record)
            saved = True
            await self._acquire(session.id)
            live = await self._watch_session(record, session)
            sandbox_id = await self._ready(record, live)
            return await self.store.update_session(
                session.id, status="idle", sandbox_id=sandbox_id
            )
        except BaseException as exc:
            sandbox_id = sandbox_id or getattr(exc, "sandbox_id", None)
            if saved and sandbox_id is None:
                with suppress(Exception):
                    record = await self.store.get_session(session.id)
                    sandbox_id = record.sandbox_id if record else None
            await self._drop_live(session.id)
            cleanup_failed = False
            if sandbox_id:
                try:
                    await self.sandbox.stop(sandbox_id)
                except Exception as cleanup_error:
                    cleanup_failed = True
                    log.error(
                        "Sandbox cleanup failed session=%s sandbox=%s error_type=%s",
                        session.id,
                        sandbox_id,
                        type(cleanup_error).__name__,
                    )
            try:
                await session.delete()
            except Exception as cleanup_error:
                cleanup_failed = True
                log.error(
                    "Upstream cleanup failed session=%s error_type=%s",
                    session.id,
                    type(cleanup_error).__name__,
                )
            if saved:
                if cleanup_failed:
                    try:
                        await self.store.update_session(
                            session.id, sandbox_id=sandbox_id, status="failed"
                        )
                    except Exception as cleanup_error:
                        log.error(
                            "Cleanup metadata unavailable session=%s "
                            "sandbox=%s error_type=%s",
                            session.id,
                            sandbox_id,
                            type(cleanup_error).__name__,
                        )
                else:
                    await self.store.delete_session(session.id)
            raise
        finally:
            await self._release(session.id)

    async def get_session(self, session_id: str, *, owner_id: str) -> SessionRecord:
        record = await self._owned(session_id, owner_id)
        live = self._live.get(session_id)
        if live is None or live.message is None:
            try:
                await self._acquire(session_id)
            except SessionConflict:
                return record
            try:
                session = (
                    live.session
                    if live
                    else await self.sdk.sessions.retrieve(session_id)
                )
                await self._reconcile(record, session)
            finally:
                await self._release(session_id)
        return await self._owned(session_id, owner_id)

    async def list_sessions(self, *, owner_id: str) -> list[SessionRecord]:
        return await self.store.list_sessions(owner_id)

    async def stream_message(
        self,
        session_id: str,
        *,
        owner_id: str,
        message_id: str,
        text: str,
        attachment_keys: tuple[str, ...] | list[str] = (),
    ) -> AsyncIterator[bytes]:
        if self._closed:
            raise SessionUnavailable("Backend is shutting down")
        record = await self._owned(session_id, owner_id)
        keys = tuple(attachment_keys)
        await self.files.validate_attachments(session_id, keys)
        old = await self.store.find_message(session_id, message_id)
        self._check_retry(old, text, keys)
        if old and old.status in _TERMINAL_MESSAGES:
            return _empty_stream()
        live = self._live.get(session_id)
        if live and live.message is not None:
            if live.message.message_id != message_id:
                raise SessionConflict("Another message is running in this session")
            return self._subscribe(live)

        await self._acquire(session_id)
        subscriber = None
        submit_attempted = False
        try:
            # Recheck after obtaining the cross-process lease.
            record = await self._owned(session_id, owner_id)
            old = await self.store.find_message(session_id, message_id)
            self._check_retry(old, text, keys)
            if old and old.status in _TERMINAL_MESSAGES:
                await self._release(session_id)
                return _empty_stream()
            session = (
                live.session if live else await self.sdk.sessions.retrieve(session_id)
            )
            info = await session.retrieve()
            await self._reconcile(record, session)
            old = await self.store.find_message(session_id, message_id)
            if old and old.status in _TERMINAL_MESSAGES:
                await self._release(session_id)
                return _empty_stream()
            if info.status == "in_progress" and old is None:
                raise SessionConflict("Another message is running in this session")
            live = await self._watch_session(record, session)
            if info.status != "in_progress":
                try:
                    await self._ready(record, live)
                except SessionUnavailable as exc:
                    if exc.sandbox_id:
                        try:
                            await self.store.update_session(
                                session_id, sandbox_id=exc.sandbox_id, status="failed"
                            )
                        except Exception as cleanup_error:
                            log.error(
                                "Restart cleanup metadata unavailable session=%s "
                                "sandbox=%s error_type=%s",
                                session_id,
                                exc.sandbox_id,
                                type(cleanup_error).__name__,
                            )
                        try:
                            await self.sandbox.stop(exc.sandbox_id)
                        except Exception as cleanup_error:
                            log.error(
                                "Restart cleanup failed session=%s "
                                "sandbox=%s error_type=%s",
                                session_id,
                                exc.sandbox_id,
                                type(cleanup_error).__name__,
                            )
                    raise
            if old is None:
                turns = await session.list_turns(limit=1, order="desc")
                previous_turn_id = turns.data[0].id if turns.data else None
                old = MessageRecord(
                    session_id=session_id,
                    message_id=message_id,
                    role="user",
                    created_at=datetime.now(UTC),
                    content={"text": text},
                    previous_turn_id=previous_turn_id,
                    attachment_keys=keys,
                    status="pending",
                )
                old = await self.store.upsert_message(old)
            live.message = old
            live.terminal = None
            subscriber = self._subscribe(live)
            await self.store.update_session(session_id, status="in_progress")
            if info.status != "in_progress" and old.turn_id is None:
                content = self._input_text(text, keys)
                submit_attempted = True
                await session.send_input(content, idempotency_key=message_id)
                if live.message is not None and live.message.status == "pending":
                    live.message = await self.store.upsert_message(
                        replace(live.message, status="submitted")
                    )
            self._check_lease(session_id)
            live.recovery = asyncio.create_task(
                self._recover_while_active(record, live)
            )
            return subscriber
        except BaseException as exc:
            if subscriber:
                await subscriber.aclose()
            rejected = (
                isinstance(exc, AgentAPIError)
                and 400 <= (exc.status_code or 0) < 500
                and exc.status_code not in {408, 409, 429}
            )
            if live and live.message is not None and submit_attempted and not rejected:
                # A lost response (or disconnected caller) does not tell us whether
                # submission succeeded. Keep persisting with the same message ID.
                if isinstance(exc, AgentAPIError):
                    live.retry_delay = 1
                live.recovery = asyncio.create_task(
                    self._recover_while_active(record, live)
                )
            else:
                if live and live.message is not None:
                    if rejected:
                        await self.store.upsert_message(
                            replace(live.message, status="failed")
                        )
                    live.message = None
                await self._release(session_id)
            raise

    @staticmethod
    def _input_text(text: str, keys: tuple[str, ...]) -> str:
        if not keys:
            return text
        paths = ["/workspace/inputs/" + key.split("/inputs/", 1)[1] for key in keys]
        return text + "\n\nAttached input files:\n" + "\n".join(paths)

    @staticmethod
    def _check_retry(
        old: MessageRecord | None, text: str, keys: tuple[str, ...]
    ) -> None:
        if old and (
            old.role != "user"
            or old.content.get("text") != text
            or old.attachment_keys != keys
        ):
            raise SessionConflict("Message ID already belongs to different content")

    async def cancel(self, session_id: str, *, owner_id: str) -> None:
        await self._owned(session_id, owner_id)
        session = await self.sdk.sessions.retrieve(session_id)
        await session.send_cancel()

    async def _watch_session(
        self, record: SessionRecord, session: AsyncAgentSession
    ) -> _LiveSession:
        live = self._live.get(record.session_id)
        if live is None or live.task is None or live.task.done():
            live = _LiveSession(session)
            self._live[record.session_id] = live
            live.task = asyncio.create_task(self._watch(record, live))
        async with asyncio.timeout(self.readiness_timeout):
            await live.opened.wait()
        if live.error:
            raise SessionUnavailable(
                "Could not subscribe to Agents API events"
            ) from live.error
        return live

    async def _watch(self, record: SessionRecord, live: _LiveSession) -> None:
        async def opened():
            live.opened.set()

        try:
            # The pinned preview SDK only exposes the HTTP-open callback here.
            # It is necessary to subscribe before starting/reconnecting the executor.
            events = self.sdk._client.stream_events(record.session_id, on_open=opened)
            async with aclosing(events):
                async for event in events:
                    await self._event(record, live, event)
            raise SessionUnavailable("Upstream event stream ended")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            live.error = exc
            live.connected.clear()
            live.opened.set()
            self._end_subscribers(live)
            # The separate recovery worker keeps persisting retained results.
            log.warning(
                "Agents API stream interrupted for session %s", record.session_id
            )

    async def _ready(self, record: SessionRecord, live: _LiveSession) -> str:
        sandbox_id = record.sandbox_id
        started_id = None
        try:
            async with asyncio.timeout(self.readiness_timeout):
                state = await self.sandbox.get(sandbox_id) if sandbox_id else None
                if state is None or state.status in {"stopped", "missing"}:
                    live.connected.clear()
                    try:
                        handle = await self.sandbox.start(
                            record.session_id,
                            record.environment_id,
                            self.bucket_name,
                            record.storage_prefix,
                            record.remote_url
                            or live.session.info.environment.remote_url,
                        )
                    except Exception as exc:
                        started_id = getattr(exc, "sandbox_id", None)
                        raise
                    sandbox_id = started_id = handle.sandbox_id
                    await self.store.update_session(
                        record.session_id, sandbox_id=sandbox_id
                    )
                elif state.status != "running":
                    raise SessionUnavailable("Existing sandbox health is not confirmed")
                elif not live.connected.is_set():
                    await self.sandbox.reconnect_executor(sandbox_id)
                while True:
                    self._check_lease(record.session_id)
                    if live.error:
                        raise SessionUnavailable(
                            "Agents API connection failed"
                        ) from live.error
                    state = await self.sandbox.get(sandbox_id)
                    if state.status != "running":
                        raise SessionUnavailable("Sandbox health is not confirmed")
                    if (
                        state.blender_ready
                        and state.executor_running
                        and live.connected.is_set()
                    ):
                        return sandbox_id
                    await asyncio.sleep(self.poll_interval)
        except Exception as exc:
            log.warning(
                "Session readiness failed session=%s sandbox=%s "
                "error_type=%s cause_type=%s",
                record.session_id,
                started_id or sandbox_id,
                type(exc).__name__,
                type(exc.__cause__).__name__ if exc.__cause__ else None,
            )
            raise SessionUnavailable(
                "Sandbox or Agents API connection is not ready", sandbox_id=started_id
            ) from exc

    async def _event(
        self, record: SessionRecord, live: _LiveSession, event: SessionEvent
    ):
        if record.session_id in self._leases:
            self._check_lease(record.session_id)
        if event.type == "session.environment.connected":
            live.connected.set()
        elif event.type in {
            "session.environment.disconnected",
            "session.environment.failed",
        }:
            live.connected.clear()
        turn = event.data.get("turn")
        subagent_id = turn.get("subagent_id") if isinstance(turn, dict) else None
        subagent_id = subagent_id or event.data.get("subagent_id")
        if subagent_id and event.turn_id:
            live.child_turns.add(event.turn_id)
        is_child = bool(subagent_id) or event.turn_id in live.child_turns
        if live.message is not None:
            if event.type == "session.turn.item.done" and event.item and not is_child:
                await self._save_item(record, event.item, turn_id=event.turn_id)
            if (
                event.type == "session.turn.created"
                and live.message.turn_id is None
                and not is_child
            ):
                live.message = await self.store.upsert_message(
                    replace(live.message, turn_id=event.turn_id, status="submitted")
                )
            if event.type in _TURN_END and event.turn_id == live.message.turn_id:
                live.terminal = _TURN_END[event.type]
            if event.type == "session.failed" and not is_child:
                live.terminal = "failed"
        terminal = (
            live.message is not None
            and not is_child
            and (
                event.type == "session.failed"
                or (event.type == "session.idle" and live.terminal is not None)
            )
        )
        if terminal:
            await self._finish(record, live, live.terminal or "failed", event=event)
        else:
            self._broadcast(live, encode_sse(event))

    async def _save_item(
        self, record: SessionRecord, item: dict, *, turn_id: str | None = None
    ):
        lease = self._leases.get(record.session_id)
        if lease is None:
            raise SessionUnavailable("Session persistence lease is not held")
        # Live events and retained-item recovery share the same lease, but may
        # race inside this process. Serialize lookup plus timestamp/key creation.
        async with lease.item_lock:
            self._check_lease(record.session_id)
            if self._leases.get(record.session_id) is not lease:
                raise SessionUnavailable("Session persistence lease changed")
            await self._write_item(record, item, turn_id=turn_id)

    async def _write_item(
        self, record: SessionRecord, item: dict, *, turn_id: str | None = None
    ):
        item_id = item.get("id")
        if (
            not isinstance(item_id, str)
            or item.get("role") == "user"
            or item.get("subagent_id")
        ):
            # User input is already stored before submission with its caller ID.
            return
        status = item.get("status", "completed")
        if status in {"in_progress", "pending"}:
            return
        item_turn_id = turn_id or item.get("turn_id")
        if item_turn_id is None:
            existing = await self.store.find_message(record.session_id, item_id)
            item_turn_id = existing.turn_id if existing else None
        created_at = item.get("created_at")
        created = (
            datetime.fromtimestamp(created_at, UTC)
            if isinstance(created_at, (int, float))
            else datetime.now(UTC)
        )
        message = MessageRecord(
            session_id=record.session_id,
            message_id=item_id,
            role=item.get("role", item.get("type", "tool")),
            content=item,
            created_at=created,
            status=status,
            item_id=item_id,
            turn_id=item_turn_id,
        )
        try:
            await self.store.upsert_message(message)
        except RecordTooLarge:
            # Upstream output may contain large images or tool results. Retain
            # its identity without letting one item block the entire chat.
            placeholder = {
                "id": item_id,
                "type": item.get("type", "unknown"),
                "role": message.role,
                "status": status,
                "content_omitted": {
                    "reason": "dynamodb_item_limit",
                    "session_id": record.session_id,
                    "item_id": item_id,
                },
            }
            await self.store.upsert_message(replace(message, content=placeholder))

    async def _reconcile(self, record: SessionRecord, session: AsyncAgentSession):
        after = None
        while True:
            page = await session.list_items(limit=100, order="asc", after=after)
            for item in page.data:
                await self._save_item(record, item)
            if not page.has_more:
                break
            next_after = page.after or (page.data[-1].get("id") if page.data else None)
            if not next_after or next_after == after:
                raise SessionUnavailable("Invalid retained-item pagination")
            after = next_after
        info = await session.retrieve()
        await self.store.update_session(record.session_id, status=info.status)
        cursor = None
        while True:
            page = await self.store.list_messages(
                record.session_id, limit=100, cursor=cursor
            )
            for message in page.messages:
                if message.role == "user" and message.status not in _TERMINAL_MESSAGES:
                    turn = await self._message_turn(session, message)
                    if turn and turn.status in _TERMINAL_MESSAGES:
                        await self.store.upsert_message(
                            replace(message, status=turn.status, turn_id=turn.id)
                        )
            if not page.next_cursor:
                break
            cursor = page.next_cursor

    async def _message_turn(self, session, message):
        if message.turn_id:
            return await session.retrieve_turn(message.turn_id)
        previous = message.previous_turn_id
        page = await session.list_turns(limit=100, order="desc")
        candidates = []
        while True:
            for turn in page.data:
                if turn.id == previous:
                    return candidates[-1] if candidates else None
                if turn.subagent_id is None:
                    candidates.append(turn)
            if not page.has_more or not page.last_id:
                return candidates[-1] if candidates and previous is None else None
            page = await session.list_turns(limit=100, order="desc", after=page.last_id)

    async def _recover_while_active(self, record: SessionRecord, live: _LiveSession):
        failures = 0
        while live.message is not None and not self._closed:
            await asyncio.sleep(max(self.poll_interval, 0.1, live.retry_delay))
            live.retry_delay = 0
            try:
                self._check_lease(record.session_id)
                message = live.message
                if message is None:
                    return
                turn = await self._message_turn(live.session, message)
                info = await live.session.retrieve()
                if (
                    turn
                    and turn.status in _TERMINAL_MESSAGES
                    and info.status != "in_progress"
                ):
                    live.message = replace(message, turn_id=turn.id)
                    await self._finish(record, live, turn.status)
                    return
                if (
                    turn is None
                    and info.status == "idle"
                    and message.status == "pending"
                ):
                    # Retrying an uncertain submission is safe with its original key.
                    await live.session.send_input(
                        self._input_text(
                            message.content["text"], message.attachment_keys
                        ),
                        idempotency_key=message.message_id,
                    )
                    if live.message is not None and live.message.status == "pending":
                        live.message = await self.store.upsert_message(
                            replace(live.message, status="submitted")
                        )
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                log.warning(
                    "Retained-output recovery interrupted for %s", record.session_id
                )
                if failures < 3:
                    live.retry_delay = 2 ** (failures - 1)
                    continue
                # Preserve pending metadata for GET or a later idempotent retry.
                live.message = None
                self._end_subscribers(live)
                await self._release(record.session_id)
                return

    async def _finish(
        self,
        record: SessionRecord,
        live: _LiveSession,
        status: str,
        *,
        event: SessionEvent | None = None,
    ):
        async with live.finishing:
            message = live.message
            if message is None:
                return
            await self._reconcile(record, live.session)
            latest = await self.store.find_message(
                record.session_id, message.message_id
            )
            turn_id = (latest.turn_id if latest else None) or message.turn_id
            await self.store.upsert_message(
                replace(message, status=status, turn_id=turn_id)
            )
            await self.store.update_session(
                record.session_id, status="failed" if status == "failed" else "idle"
            )
            if event:
                self._broadcast(live, encode_sse(event))
            self._end_subscribers(live)
            live.message = None
            if live.recovery and live.recovery is not asyncio.current_task():
                live.recovery.cancel()
            await self._release(record.session_id)

    def _subscribe(self, live: _LiveSession) -> _Subscription:
        return _Subscription(live, self.subscriber_queue_size)

    @staticmethod
    def _broadcast(live: _LiveSession, chunk: bytes):
        for queue in tuple(live.subscribers):
            if queue.full():
                # Drop a slow delivery channel, never the persistence producer.
                live.subscribers.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(chunk)

    @staticmethod
    def _end_subscribers(live: _LiveSession):
        for queue in tuple(live.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(None)
        live.subscribers.clear()

    async def _acquire(self, session_id: str):
        if (lease := self._leases.get(session_id)) and lease.lost:
            await self._release(session_id)
        if session_id in self._leases:
            raise SessionConflict("Session is busy")
        lease = _Lease(uuid4().hex)
        if not await self.store.acquire_lease(
            session_id, lease.token, ttl_seconds=self.lease_seconds
        ):
            raise SessionConflict(
                "Session is busy; retry after its active operation finishes"
            )
        self._leases[session_id] = lease
        lease.heartbeat = asyncio.create_task(self._renew(session_id, lease))

    async def _renew(self, session_id: str, lease: _Lease):
        try:
            while True:
                await asyncio.sleep(self.lease_seconds / 3)
                if not await self.store.renew_lease(
                    session_id, lease.token, ttl_seconds=self.lease_seconds
                ):
                    raise SessionUnavailable("Session lease was lost")
        except asyncio.CancelledError:
            raise
        except Exception:
            lease.lost = True
            live = self._live.get(session_id)
            if live:
                live.message = None
                self._end_subscribers(live)
                if live.task:
                    live.task.cancel()
                if live.recovery:
                    live.recovery.cancel()
            log.warning("Session lease lost for %s; stopped local producer", session_id)

    def _check_lease(self, session_id: str):
        lease = self._leases.get(session_id)
        if lease and lease.lost:
            raise SessionUnavailable("Session lease was lost")

    async def _release(self, session_id: str):
        lease = self._leases.pop(session_id, None)
        if lease:
            if lease.heartbeat and lease.heartbeat is not asyncio.current_task():
                lease.heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await lease.heartbeat
            await self.store.release_lease(session_id, lease.token)

    async def _drop_live(self, session_id: str):
        live = self._live.pop(session_id, None)
        if live:
            self._end_subscribers(live)
            tasks = [task for task in (live.task, live.recovery) if task]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            async with asyncio.timeout(self.shutdown_timeout):
                while any(live.message is not None for live in self._live.values()):
                    await asyncio.sleep(0.01)
        except TimeoutError:
            pass
        for session_id in list(self._live):
            await self._drop_live(session_id)
        for session_id in list(self._leases):
            await self._release(session_id)

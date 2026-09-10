"""Modal lifecycle adapter for the separately published Blender runtime.

The image's launch command must supervise Blender/MCP and the executor. Its
health command must execute a real Blender/MCP check and print a JSON object
with boolean ``blender_ready`` and ``executor_running`` fields. Local process
health does not prove the executor has connected to OpenAI; session
orchestration waits for that separately.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import modal
from modal.exception import Error as ModalError
from modal.exception import NotFoundError


@dataclass(frozen=True)
class SandboxCredentials:
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    session_token: str = field(repr=False)
    expires_at: datetime | None = None


@dataclass(frozen=True)
class SandboxHandle:
    sandbox_id: str


@dataclass(frozen=True)
class SandboxState:
    sandbox_id: str
    status: Literal["running", "stopped", "unhealthy", "unknown", "missing"]
    blender_ready: bool = False
    executor_running: bool = False
    exit_code: int | None = None


class SandboxUnavailable(RuntimeError):
    """The named runtime or its required configuration is unavailable."""


class SandboxStartupError(SandboxUnavailable):
    """Startup failed; the identifier also allows cleanup to be retried."""

    def __init__(self, message: str, sandbox_id: str):
        super().__init__(message)
        self.sandbox_id = sandbox_id


class SandboxService:
    def __init__(
        self,
        *,
        launch_command: tuple[str, ...] = (),
        health_command: tuple[str, ...] = (),
        reconnect_command: tuple[str, ...] = (),
        executor_secret_name: str = "",
        s3_credentials: Callable[[str, str], Awaitable[SandboxCredentials]]
        | None = None,
        image_name: str = "astra-blender:v1",
        app_name: str = "astra-interior-designer-blender",
        aws_region: str = "us-east-1",
        remote_url: str = "https://api.openai.com/v1/agents/api",
        timeout_seconds: int = 3600,
        readiness_timeout_seconds: float = 180,
        poll_interval_seconds: float = 1,
    ):
        self.launch_command = launch_command
        self.health_command = health_command
        self.reconnect_command = reconnect_command
        self.executor_secret_name = executor_secret_name
        self.s3_credentials = s3_credentials
        self.image_name = image_name
        self.app_name = app_name
        self.aws_region = aws_region
        self.remote_url = remote_url
        self.timeout_seconds = timeout_seconds
        self.readiness_timeout_seconds = readiness_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    async def start(
        self,
        session_id: str,
        environment_id: str,
        bucket_name: str,
        storage_prefix: str,
    ) -> SandboxHandle:
        if not session_id or "/" in session_id or not environment_id or not bucket_name:
            raise ValueError(
                "Session, environment, and bucket identifiers are required"
            )
        if storage_prefix != f"sandboxes/{session_id}/":
            raise ValueError("Storage prefix must belong to the session")
        if (
            not self.launch_command
            or not self.health_command
            or not self.executor_secret_name
            or self.s3_credentials is None
        ):
            raise SandboxUnavailable(
                "Configure the published runtime commands, restricted executor secret, "
                "and session-scoped S3 credentials before starting a sandbox"
            )

        image = modal.Image.from_name(self.image_name)
        credentials = await self.s3_credentials(bucket_name, storage_prefix)
        secret = {
            "AWS_ACCESS_KEY_ID": credentials.access_key_id,
            "AWS_SECRET_ACCESS_KEY": credentials.secret_access_key,
            "AWS_SESSION_TOKEN": credentials.session_token,
        }
        if not all(secret.values()):
            raise SandboxUnavailable(
                "Session-scoped temporary S3 credentials are required"
            )
        timeout = self.timeout_seconds
        if credentials.expires_at is not None:
            if credentials.expires_at.tzinfo is None:
                raise SandboxUnavailable("S3 credential expiry must include a timezone")
            remaining = (credentials.expires_at - datetime.now(UTC)).total_seconds()
            timeout = min(timeout, int(remaining - 300))
        if timeout <= 0:
            raise SandboxUnavailable("S3 credentials expire too soon to start compute")

        app = await modal.App.lookup.aio(self.app_name, create_if_missing=True)
        create = asyncio.create_task(
            modal.Sandbox.create.aio(
                *self.launch_command,
                app=app,
                image=image,
                gpu="RTX-PRO-6000",
                cpu=4,
                memory=16384,
                timeout=timeout,
                workdir="/workspace",
                tags={"project": "astra-interior-designer", "session_id": session_id},
                env={
                    "SESSION_ID": session_id,
                    "ENVIRONMENT_ID": environment_id,
                    "S3_BUCKET": bucket_name,
                    "S3_PREFIX": storage_prefix,
                    "AWS_REGION": self.aws_region,
                    "AWS_DEFAULT_REGION": self.aws_region,
                    "AGENTS_REMOTE_URL": self.remote_url,
                },
                secrets=[
                    modal.Secret.from_dict(secret),
                    modal.Secret.from_name(self.executor_secret_name),
                ],
            )
        )
        cancelled = False
        try:
            sandbox = await asyncio.shield(create)
        except NotFoundError as exc:
            raise SandboxUnavailable(
                "The configured Modal sandbox image or executor secret is unavailable"
            ) from exc
        except asyncio.CancelledError:
            # Finish obtaining the provider ID so cancellation cannot orphan a GPU.
            sandbox = await create
            cancelled = True
        try:
            if cancelled:
                raise asyncio.CancelledError
            await self._wait_ready(sandbox)
            return SandboxHandle(sandbox_id=sandbox.object_id)
        except BaseException as exc:
            try:
                await asyncio.shield(sandbox.terminate.aio(wait=True))
            except Exception as cleanup_error:
                raise SandboxStartupError(
                    "Sandbox startup failed and compute cleanup must be retried",
                    sandbox.object_id,
                ) from cleanup_error
            if isinstance(exc, Exception) and not isinstance(exc, SandboxStartupError):
                raise SandboxStartupError(
                    "Sandbox runtime failed during startup", sandbox.object_id
                ) from exc
            raise
        finally:
            await sandbox.detach.aio()

    async def get(self, sandbox_id: str) -> SandboxState:
        try:
            sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
        except NotFoundError:
            return SandboxState(sandbox_id=sandbox_id, status="missing")
        try:
            return await self._inspect(sandbox)
        finally:
            await sandbox.detach.aio()

    async def stop(self, sandbox_id: str) -> None:
        try:
            sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
        except NotFoundError:
            return
        try:
            await sandbox.terminate.aio(wait=True)
        except NotFoundError:
            pass
        finally:
            await sandbox.detach.aio()

    async def reconnect_executor(self, sandbox_id: str) -> None:
        """Restart only the executor while retaining the live Blender workspace.

        Subscribe to OpenAI events before calling, then wait for an environment
        connected event. Successful local health alone is not that proof.
        """
        if not self.reconnect_command or not self.health_command:
            raise SandboxUnavailable(
                "Configure the executor reconnect and health commands"
            )
        sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
        try:
            if await sandbox.poll.aio() is not None:
                raise SandboxUnavailable(
                    "Cannot reconnect an executor in a stopped sandbox"
                )
            process = await sandbox.exec.aio(*self.reconnect_command, timeout=30)
            _, _, result = await asyncio.gather(
                process.stdout.read.aio(),
                process.stderr.read.aio(),
                process.wait.aio(),
            )
            if result != 0:
                raise SandboxUnavailable("Executor reconnect command failed")
            await self._wait_ready(sandbox)
        finally:
            await sandbox.detach.aio()

    async def _wait_ready(self, sandbox) -> None:
        try:
            async with asyncio.timeout(self.readiness_timeout_seconds):
                while True:
                    state = await self._inspect(sandbox)
                    if state.status == "running":
                        return
                    if state.status == "stopped":
                        raise SandboxStartupError(
                            "Sandbox exited before Blender and executor were ready",
                            sandbox.object_id,
                        )
                    await asyncio.sleep(self.poll_interval_seconds)
        except TimeoutError as exc:
            raise SandboxStartupError(
                "Timed out waiting for Blender and executor readiness",
                sandbox.object_id,
            ) from exc

    async def _inspect(self, sandbox) -> SandboxState:
        exit_code = await sandbox.poll.aio()
        if exit_code is not None:
            return SandboxState(sandbox.object_id, "stopped", exit_code=exit_code)
        if not self.health_command:
            return SandboxState(sandbox.object_id, "unknown")
        try:
            async with asyncio.timeout(10):
                process = await sandbox.exec.aio(*self.health_command, timeout=10)
                output, _, result = await asyncio.gather(
                    process.stdout.read.aio(),
                    process.stderr.read.aio(),
                    process.wait.aio(),
                )
            if result != 0:
                # A failed probe is not proof Blender died. In particular, Modal
                # returns -1 when a command exceeds its execution deadline.
                return SandboxState(sandbox.object_id, "unknown")
            health = json.loads(output)
            blender_ready = health.get("blender_ready")
            executor_running = health.get("executor_running")
            if not isinstance(blender_ready, bool) or not isinstance(
                executor_running, bool
            ):
                return SandboxState(sandbox.object_id, "unknown")
            return SandboxState(
                sandbox_id=sandbox.object_id,
                status="running" if blender_ready and executor_running else "unhealthy",
                blender_ready=blender_ready,
                executor_running=executor_running,
            )
        except (TimeoutError, ValueError, AttributeError, ModalError):
            # Blender's main thread may be busy rendering. Leave existing
            # compute and its scene alone until health can be confirmed.
            return SandboxState(sandbox.object_id, "unknown")

"""Construct application clients at startup and close them together."""

import asyncio
import hashlib
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from openai import AsyncOpenAI

from astra_interior_designer.config import ConfigError, Settings
from astra_interior_designer.services.sandbox import SandboxCredentials, SandboxService
from astra_interior_designer.services.sessions import SessionService
from astra_interior_designer.services.storage import (
    DynamoStorage,
    S3Storage,
    session_prefix,
)


@dataclass
class Services:
    storage: DynamoStorage
    files: S3Storage
    sandbox: SandboxService
    sessions: SessionService
    _cleanup: AsyncExitStack = field(default_factory=AsyncExitStack, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.sessions.close()
        finally:
            await self._cleanup.aclose()


async def build_services(settings: Settings) -> Services:
    for name in ("openai_api_key", "app_api_key"):
        value = getattr(settings, name)
        if value is None or not value.get_secret_value().strip():
            raise ConfigError(f"{name.upper()} is required")
    signing_key = settings.s3_signing_access_key_id
    signing_secret = settings.s3_signing_secret_access_key
    if (signing_key is not None or signing_secret is not None) and (
        signing_key is None
        or signing_secret is None
        or not signing_key.get_secret_value().strip()
        or not signing_secret.get_secret_value().strip()
    ):
        raise ConfigError(
            "Both S3_SIGNING credential fields must be configured together"
        )

    cleanup = AsyncExitStack()
    try:
        aws = await asyncio.to_thread(
            boto3.Session,
            profile_name=settings.aws_profile,
            region_name=settings.aws_region,
        )

        async def client(service: str, **kwargs):
            created = await asyncio.to_thread(
                aws.client,
                service,
                config=Config(
                    signature_version="s3v4" if service == "s3" else "v4",
                    connect_timeout=10,
                    read_timeout=30,
                    retries={"mode": "standard", "max_attempts": 3},
                ),
                **kwargs,
            )
            cleanup.push_async_callback(asyncio.to_thread, created.close)
            return created

        dynamo = await client("dynamodb")
        s3 = await client("s3")
        sts = await client("sts")
        signer = s3
        if signing_key is not None and signing_secret is not None:
            signer = await client(
                "s3",
                aws_access_key_id=signing_key.get_secret_value(),
                aws_secret_access_key=signing_secret.get_secret_value(),
            )

        storage = DynamoStorage(
            client=dynamo,
            sessions_table=settings.sessions_table,
            messages_table=settings.messages_table,
        )
        files = S3Storage(
            client=s3,
            bucket_name=settings.s3_bucket,
            signing_client=signer,
        )

        async def sandbox_credentials(
            bucket_name: str, storage_prefix: str
        ) -> SandboxCredentials:
            parts = storage_prefix.split("/")
            if (
                bucket_name != settings.s3_bucket
                or len(parts) != 3
                or storage_prefix != session_prefix(parts[1])
            ):
                raise ValueError(
                    "Sandbox storage must be scoped to this app and session"
                )
            if not settings.sandbox_s3_role_arn:
                raise ConfigError("SANDBOX_S3_ROLE_ARN is required to start compute")
            bucket_arn = f"arn:aws:s3:::{bucket_name}"
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "s3:ListBucket",
                        "Resource": bucket_arn,
                        "Condition": {
                            "StringLike": {
                                "s3:prefix": [
                                    f"{storage_prefix}inputs/",
                                    f"{storage_prefix}inputs/*",
                                    f"{storage_prefix}scene.glb",
                                    f"{storage_prefix}render.png",
                                ]
                            }
                        },
                    },
                    {
                        "Effect": "Allow",
                        "Action": "s3:GetObject",
                        "Resource": f"{bucket_arn}/{storage_prefix}inputs/*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject"],
                        "Resource": [
                            f"{bucket_arn}/{storage_prefix}scene.glb",
                            f"{bucket_arn}/{storage_prefix}render.png",
                        ],
                    },
                ],
            }
            suffix = hashlib.sha256(storage_prefix.encode()).hexdigest()[:24]
            try:
                response = await asyncio.to_thread(
                    sts.assume_role,
                    RoleArn=settings.sandbox_s3_role_arn,
                    RoleSessionName=f"astra-{suffix}",
                    Policy=json.dumps(policy, separators=(",", ":")),
                    DurationSeconds=3600,
                )
            except (BotoCoreError, ClientError):
                raise ConfigError(
                    "Unable to assume the configured sandbox S3 role"
                ) from None
            temporary = response["Credentials"]
            return SandboxCredentials(
                access_key_id=temporary["AccessKeyId"],
                secret_access_key=temporary["SecretAccessKey"],
                session_token=temporary["SessionToken"],
                expires_at=temporary["Expiration"],
            )

        sandbox = SandboxService(
            launch_command=settings.modal_launch_command,
            health_command=settings.modal_health_command,
            reconnect_command=settings.modal_reconnect_command,
            sync_inputs_command=settings.modal_sync_inputs_command,
            executor_secret_name=settings.modal_executor_secret_name,
            s3_credentials=sandbox_credentials,
            image_name=settings.modal_image,
            aws_region=settings.aws_region,
            timeout_seconds=settings.sandbox_timeout_seconds,
            readiness_timeout_seconds=settings.readiness_timeout_seconds,
        )
        sdk = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=600.0,
        )
        cleanup.push_async_callback(sdk.close)
        sessions = SessionService(
            storage,
            files,
            sandbox,
            sdk,
            bucket_name=settings.s3_bucket,
            model=settings.agent_model,
            readiness_timeout=settings.readiness_timeout_seconds,
        )
        return Services(storage, files, sandbox, sessions, _cleanup=cleanup)
    except BaseException:
        await cleanup.aclose()
        raise

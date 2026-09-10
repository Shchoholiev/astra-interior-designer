"""Startup configuration with optional AWS Secrets Manager credentials.

Precedence: explicit Settings values > environment > local .env > Secrets
Manager > defaults. AWS_SECRET_ID selects one JSON secret, fetched once by
load_settings at startup. Only the four credential fields below are accepted
from that secret; runtime commands and AWS resource selection stay in config.
"""

import asyncio
import json

import boto3
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError


class ConfigError(RuntimeError):
    """Configuration cannot satisfy the application's runtime contract."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    app_api_key: SecretStr | None = Field(default=None, repr=False)
    s3_signing_access_key_id: SecretStr | None = Field(default=None, repr=False)
    s3_signing_secret_access_key: SecretStr | None = Field(default=None, repr=False)

    aws_secret_id: str | None = None
    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    sessions_table: str = "astra-interior-designer-sessions"
    messages_table: str = "astra-interior-designer-messages"
    s3_bucket: str = "astra-interior-designer-files-022104542793"
    agent_model: str = "gpt-6-astra"
    cors_origins: tuple[str, ...] = ()

    modal_image: str = "astra-blender:v6"
    modal_launch_command: tuple[str, ...] = ()
    modal_health_command: tuple[str, ...] = ()
    modal_reconnect_command: tuple[str, ...] = ()
    modal_sync_inputs_command: tuple[str, ...] = ()
    modal_executor_secret_name: str = ""
    sandbox_s3_role_arn: str | None = None
    sandbox_timeout_seconds: int = Field(default=3600, gt=0)
    readiness_timeout_seconds: float = Field(default=180, gt=0)


_SECRET_FIELDS = {
    "OPENAI_API_KEY": "openai_api_key",
    "APP_API_KEY": "app_api_key",
    "S3_SIGNING_ACCESS_KEY_ID": "s3_signing_access_key_id",
    "S3_SIGNING_SECRET_ACCESS_KEY": "s3_signing_secret_access_key",
}


def _read_secret(settings: Settings) -> dict[str, SecretStr]:
    client = None
    try:
        aws = boto3.Session(
            profile_name=settings.aws_profile, region_name=settings.aws_region
        )
        client = aws.client("secretsmanager")
        response = client.get_secret_value(SecretId=settings.aws_secret_id)
        payload = json.loads(response["SecretString"])
        if not isinstance(payload, dict):
            raise ConfigError("AWS secret must contain a JSON object")
        selected = {}
        for name, field in _SECRET_FIELDS.items():
            if name not in payload:
                continue
            value = payload[name]
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(
                    "AWS secret credential values must be nonempty strings"
                )
            selected[field] = SecretStr(value)
        return selected
    except ConfigError:
        raise
    except Exception:
        # Neither the AWS response nor validation errors may expose secret content.
        raise ConfigError("Unable to load the configured AWS JSON secret") from None
    finally:
        if client is not None:
            client.close()


async def load_settings(settings: Settings | None = None) -> Settings:
    """Resolve one startup snapshot; never fetch secrets during an HTTP request."""
    try:
        resolved = settings if settings is not None else Settings()
    except (ValidationError, SettingsError):
        raise ConfigError("Invalid application configuration") from None
    if not resolved.aws_secret_id:
        return resolved
    secret_values = await asyncio.to_thread(_read_secret, resolved)
    overrides = {
        key: value
        for key, value in secret_values.items()
        if key not in resolved.model_fields_set
    }
    return resolved.model_copy(update=overrides)

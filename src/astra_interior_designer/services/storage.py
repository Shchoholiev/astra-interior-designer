"""Session metadata and chat in DynamoDB; private session files in S3."""

import asyncio
import base64
import binascii
import json
import re
import time
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

type JSONValue = (
    None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]
)


class StorageConflict(RuntimeError):
    """A conditional write could not safely be performed."""


class InvalidCursor(ValueError):
    """A pagination cursor is malformed or belongs to another session."""


class RecordTooLarge(ValueError):
    """An item exceeds the application's conservative DynamoDB size limit."""


class StorageConfigurationError(RuntimeError):
    """Storage credentials or configuration cannot satisfy the API contract."""


class SigningCredentialsTooShort(StorageConfigurationError):
    """Signing credentials cannot cover the promised URL lifetime."""


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def session_prefix(session_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("Invalid session ID")
    return f"sandboxes/{session_id}/"


@dataclass(frozen=True, kw_only=True)
class SessionRecord:
    session_id: str
    environment_id: str
    storage_prefix: str
    remote_url: str | None = None
    status: str = "starting"
    sandbox_id: str | None = None
    owner_id: str | None = None
    title: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, kw_only=True)
class MessageRecord:
    session_id: str
    message_id: str
    role: str
    content: JSONValue
    created_at: datetime
    status: str = "completed"
    item_id: str | None = None
    turn_id: str | None = None
    previous_turn_id: str | None = None
    attachment_keys: tuple[str, ...] = ()

    @property
    def message_key(self) -> str:
        return f"{_timestamp(self.created_at)}#{self.message_id}"


@dataclass(frozen=True)
class MessagePage:
    messages: list[MessageRecord]
    next_cursor: str | None


def _encode(item: dict[str, Any]) -> dict[str, Any]:
    serialized = {key: TypeSerializer().serialize(value) for key, value in item.items()}
    # A conservative wire-size cap leaves room below DynamoDB's 400 KiB item limit.
    if len(json.dumps(serialized, ensure_ascii=False).encode()) > 380 * 1024:
        raise RecordTooLarge("Message or metadata exceeds the 380 KiB storage limit")
    return serialized


def _decode(item: dict[str, Any]) -> dict[str, Any]:
    return {key: TypeDeserializer().deserialize(value) for key, value in item.items()}


def _session(item: dict[str, Any]) -> SessionRecord:
    decoded = _decode(item)
    selected = {
        f.name: decoded[f.name] for f in fields(SessionRecord) if f.name in decoded
    }
    for key in ("created_at", "updated_at"):
        selected[key] = datetime.fromisoformat(selected[key])
    return SessionRecord(**selected)


def _message(item: dict[str, Any]) -> MessageRecord:
    decoded = _decode(item)
    decoded.pop("message_key")
    decoded["content"] = json.loads(decoded.pop("content_json"))
    decoded["created_at"] = datetime.fromisoformat(decoded["created_at"])
    decoded["attachment_keys"] = tuple(decoded.get("attachment_keys", ()))
    return MessageRecord(**decoded)


def _conditional_failure(error: ClientError) -> bool:
    return error.response["Error"]["Code"] == "ConditionalCheckFailedException"


class DynamoStorage:
    def __init__(self, *, client: Any, sessions_table: str, messages_table: str):
        self.client = client
        self.sessions_table = sessions_table
        self.messages_table = messages_table

    async def create_session(self, record: SessionRecord) -> None:
        if record.storage_prefix != session_prefix(record.session_id):
            raise ValueError("Storage prefix must match the session")
        item = asdict(record)
        item["created_at"] = _timestamp(record.created_at)
        item["updated_at"] = _timestamp(record.updated_at)
        try:
            await asyncio.to_thread(
                self.client.put_item,
                TableName=self.sessions_table,
                Item=_encode(item),
                ConditionExpression="attribute_not_exists(session_id)",
            )
        except ClientError as error:
            if _conditional_failure(error):
                raise StorageConflict("Session already exists") from error
            raise

    async def get_session(self, session_id: str) -> SessionRecord | None:
        response = await asyncio.to_thread(
            self.client.get_item,
            TableName=self.sessions_table,
            Key={"session_id": {"S": session_id}},
            ConsistentRead=True,
        )
        return _session(response["Item"]) if "Item" in response else None

    async def list_sessions(self, owner_id: str) -> list[SessionRecord]:
        """List one owner's sessions, newest activity first.

        The current product has one owner and no owner index. Keep this scan behind
        the storage interface so it can move to a GSI without changing the API.
        """
        arguments: dict[str, Any] = {
            "TableName": self.sessions_table,
            "FilterExpression": "owner_id = :owner",
            "ExpressionAttributeValues": {":owner": {"S": owner_id}},
            "ConsistentRead": True,
        }
        records: list[SessionRecord] = []
        while True:
            response = await asyncio.to_thread(self.client.scan, **arguments)
            records.extend(_session(item) for item in response.get("Items", []))
            key = response.get("LastEvaluatedKey")
            if not key:
                break
            arguments["ExclusiveStartKey"] = key
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    async def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        sandbox_id: str | None = None,
    ) -> SessionRecord:
        updates = {"updated_at": _timestamp(_now())}
        if status is not None:
            updates["status"] = status
        if sandbox_id is not None:
            updates["sandbox_id"] = sandbox_id
        names = {f"#f{index}": key for index, key in enumerate(updates)}
        values = {f":v{index}": value for index, value in enumerate(updates.values())}
        expression = ", ".join(f"#f{i} = :v{i}" for i in range(len(updates)))
        try:
            response = await asyncio.to_thread(
                self.client.update_item,
                TableName=self.sessions_table,
                Key={"session_id": {"S": session_id}},
                UpdateExpression=f"SET {expression}",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=_encode(values),
                ConditionExpression="attribute_exists(session_id)",
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            if _conditional_failure(error):
                raise StorageConflict("Session no longer exists") from error
            raise
        return _session(response["Attributes"])

    async def delete_session(self, session_id: str) -> None:
        """Remove metadata during failed creation, before messages can be submitted."""
        await asyncio.to_thread(
            self.client.delete_item,
            TableName=self.sessions_table,
            Key={"session_id": {"S": session_id}},
        )

    async def _lease_write(self, session_id: str, **arguments: Any) -> bool:
        try:
            await asyncio.to_thread(
                self.client.update_item,
                TableName=self.sessions_table,
                Key={"session_id": {"S": session_id}},
                **arguments,
            )
        except ClientError as error:
            if _conditional_failure(error):
                return False
            raise
        return True

    async def acquire_lease(
        self, session_id: str, owner: str, *, ttl_seconds: int = 120
    ) -> bool:
        if not owner or ttl_seconds < 1:
            raise ValueError("Lease owner and positive duration are required")
        now = int(time.time())
        return await self._lease_write(
            session_id,
            UpdateExpression="SET lease_owner = :owner, lease_expires_at = :expires",
            ConditionExpression=(
                "attribute_exists(session_id) AND (attribute_not_exists(lease_owner) "
                "OR lease_expires_at <= :now OR lease_owner = :owner)"
            ),
            ExpressionAttributeValues=_encode(
                {":owner": owner, ":expires": now + ttl_seconds, ":now": now}
            ),
        )

    async def renew_lease(
        self, session_id: str, owner: str, *, ttl_seconds: int = 120
    ) -> bool:
        if not owner or ttl_seconds < 1:
            raise ValueError("Lease owner and positive duration are required")
        now = int(time.time())
        return await self._lease_write(
            session_id,
            UpdateExpression="SET lease_expires_at = :expires",
            ConditionExpression="lease_owner = :owner AND lease_expires_at > :now",
            ExpressionAttributeValues=_encode(
                {":owner": owner, ":expires": now + ttl_seconds, ":now": now}
            ),
        )

    async def release_lease(self, session_id: str, owner: str) -> None:
        await self._lease_write(
            session_id,
            UpdateExpression="REMOVE lease_owner, lease_expires_at",
            ConditionExpression="lease_owner = :owner",
            ExpressionAttributeValues={":owner": {"S": owner}},
        )

    async def upsert_message(self, record: MessageRecord) -> MessageRecord:
        """Reuse the first key on retries. Create messages under the session lease."""
        session_prefix(record.session_id)
        if not record.message_id or len(record.message_id.encode()) > 256:
            raise ValueError("Message ID must contain between 1 and 256 bytes")
        content = json.dumps(record.content, ensure_ascii=False, allow_nan=False)
        # Validate size before even reading the old item; failed writes leave it intact.
        item = asdict(record)
        item.pop("content")
        item["content_json"] = content
        item["created_at"] = _timestamp(record.created_at)
        item["message_key"] = record.message_key
        _encode(item)
        existing = await self.find_message(record.session_id, record.message_id)
        if existing is not None:
            record = replace(record, created_at=existing.created_at)
            item["created_at"] = _timestamp(record.created_at)
            item["message_key"] = record.message_key
        await asyncio.to_thread(
            self.client.put_item, TableName=self.messages_table, Item=_encode(item)
        )
        return record

    async def find_message(
        self, session_id: str, message_id: str
    ) -> MessageRecord | None:
        arguments: dict[str, Any] = {
            "TableName": self.messages_table,
            "KeyConditionExpression": "session_id = :session",
            "FilterExpression": "message_id = :message",
            "ExpressionAttributeValues": {
                ":session": {"S": session_id},
                ":message": {"S": message_id},
            },
            "ConsistentRead": True,
        }
        while True:
            response = await asyncio.to_thread(self.client.query, **arguments)
            if response.get("Items"):
                return _message(response["Items"][0])
            if not response.get("LastEvaluatedKey"):
                return None
            arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    async def list_messages(
        self, session_id: str, *, limit: int = 50, cursor: str | None = None
    ) -> MessagePage:
        if not 1 <= limit <= 100:
            raise ValueError("Message page size must be between 1 and 100")
        arguments: dict[str, Any] = {
            "TableName": self.messages_table,
            "KeyConditionExpression": "session_id = :session",
            "ExpressionAttributeValues": {":session": {"S": session_id}},
            "ScanIndexForward": True,
            "ConsistentRead": True,
            "Limit": limit,
        }
        if cursor is not None:
            try:
                if len(cursor) > 4096:
                    raise ValueError
                decoded = json.loads(
                    base64.b64decode(cursor, altchars=b"-_", validate=True)
                )
                if (
                    set(decoded) != {"session_id", "message_key"}
                    or decoded["session_id"] != session_id
                    or not isinstance(decoded["message_key"], str)
                    or not 1 <= len(decoded["message_key"].encode()) <= 1024
                ):
                    raise ValueError
                arguments["ExclusiveStartKey"] = _encode(decoded)
            except (ValueError, TypeError, binascii.Error, UnicodeError) as error:
                raise InvalidCursor("Invalid cursor for this session") from error
        response = await asyncio.to_thread(self.client.query, **arguments)
        next_cursor = None
        if key := response.get("LastEvaluatedKey"):
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(_decode(key)).encode()
            ).decode()
        return MessagePage(
            messages=[_message(item) for item in response.get("Items", [])],
            next_cursor=next_cursor,
        )


@dataclass(frozen=True)
class SignedDownload:
    url: str
    expires_at: datetime


@dataclass(frozen=True)
class SignedRender(SignedDownload):
    sha256: str


@dataclass(frozen=True)
class SignedUpload:
    object_key: str
    url: str
    headers: dict[str, str]
    expires_at: datetime


class S3Storage:
    def __init__(
        self,
        *,
        client: Any,
        bucket_name: str,
        signing_client: Any | None = None,
        signing_credentials_expires_at: datetime | None = None,
    ):
        self.client = client
        self.bucket_name = bucket_name
        self.signing_client = signing_client if signing_client is not None else client
        self.signing_credentials_expires_at = signing_credentials_expires_at

    async def _exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket_name, Key=key
            )
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def _sign(
        self,
        operation: str,
        parameters: dict[str, str],
        ttl: int,
        *,
        cap_to_credentials: bool = False,
    ) -> SignedDownload:
        credentials = self.signing_client._request_signer._credentials
        if credentials is None:
            raise StorageConfigurationError("S3 signing credentials are missing")
        frozen = credentials.get_frozen_credentials()
        expirations = [
            expiration
            for expiration in (
                self.signing_credentials_expires_at,
                getattr(credentials, "_expiry_time", None),
            )
            if expiration is not None
        ]
        for expiration in expirations:
            _timestamp(expiration)
        if cap_to_credentials and expirations:
            remaining = int((min(expirations) - _now()).total_seconds()) - 5
            ttl = min(ttl, remaining)
            if ttl < 1:
                raise SigningCredentialsTooShort(
                    "S3 signing credentials expire too soon to issue an upload URL"
                )
        url = self.signing_client.generate_presigned_url(
            operation,
            Params={"Bucket": self.bucket_name, **parameters},
            ExpiresIn=ttl,
        )
        query = parse_qs(urlsplit(url).query)
        if "X-Amz-Date" in query:
            signed_at = datetime.strptime(
                query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=UTC)
            expires_at = signed_at + timedelta(seconds=int(query["X-Amz-Expires"][0]))
        elif "Expires" in query:
            expires_at = datetime.fromtimestamp(int(query["Expires"][0]), UTC)
        else:
            raise StorageConfigurationError("Cannot determine S3 URL expiry")
        if (frozen.token and not expirations) or any(
            expiration < expires_at for expiration in expirations
        ):
            raise SigningCredentialsTooShort(
                f"S3 signing credentials must remain valid for {ttl} seconds. "
                "Configure a separate signing client with sufficient lifetime; "
                "temporary credentials require a known expiry."
            )
        return SignedDownload(url=url, expires_at=expires_at)

    async def scene_url(self, session_id: str) -> SignedDownload | None:
        key = f"{session_prefix(session_id)}scene.glb"
        if not await self._exists(key):
            return None
        return await asyncio.to_thread(self._sign, "get_object", {"Key": key}, 43_200)

    async def render_url(self, session_id: str) -> SignedRender | None:
        key = f"{session_prefix(session_id)}render.png"
        try:
            metadata = await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket_name, Key=key
            )
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        digest = metadata.get("Metadata", {}).get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise StorageConfigurationError("Render is missing its SHA-256 metadata")
        signed = await asyncio.to_thread(self._sign, "get_object", {"Key": key}, 43_200)
        return SignedRender(signed.url, signed.expires_at, digest)

    async def upload_url(
        self, session_id: str, filename: str, content_type: str
    ) -> SignedUpload:
        prefix = session_prefix(session_id)
        if (
            not content_type
            or len(content_type) > 256
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in content_type
            )
        ):
            raise ValueError("A valid content type is required")
        basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        basename = re.sub(r"[^A-Za-z0-9._-]", "_", basename)[:120].strip(".")
        basename = basename.replace("..", "_") or "upload.bin"
        key = f"{prefix}inputs/{uuid4().hex}-{basename}"
        signed = await asyncio.to_thread(
            self._sign,
            "put_object",
            {"Key": key, "ContentType": content_type},
            900,
            cap_to_credentials=True,
        )
        return SignedUpload(
            object_key=key,
            url=signed.url,
            headers={"Content-Type": content_type},
            expires_at=signed.expires_at,
        )

    async def validate_attachments(self, session_id: str, keys: list[str]) -> None:
        prefix = f"{session_prefix(session_id)}inputs/"
        for key in keys:
            if (
                not key.startswith(prefix)
                or key == prefix
                or "\\" in key
                or any(part in (".", "..", "") for part in key.split("/"))
                or len(key.encode()) > 1024
            ):
                raise ValueError(
                    "Attachments must belong to this session's inputs folder"
                )
            if not await self._exists(key):
                raise FileNotFoundError("Attachment has not been uploaded")

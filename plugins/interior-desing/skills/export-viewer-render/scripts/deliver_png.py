"""Local PNG promotion and supervisor-receipt checks; no cloud credentials."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from PIL import Image


def promote_png(source, destination, *, width, height):
    """Validate an immutable copy, then atomically replace the delivery PNG."""
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with (
            os.fdopen(descriptor, "rb") as incoming,
            tempfile.NamedTemporaryFile(
                mode="w+b", dir=destination.parent, prefix=".render-", delete=False
            ) as output,
        ):
            temporary = Path(output.name)
            before = os.fstat(incoming.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Render source must be a regular file")
            shutil.copyfileobj(incoming, output)
            after = os.fstat(incoming.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise ValueError("Render changed during promotion")
            output.flush()
            output.seek(0)
            with Image.open(output, formats=("PNG",)) as image:
                image.verify()
            output.seek(0)
            with Image.open(output, formats=("PNG",)) as image:
                image.load()
                if image.size != (width, height):
                    raise ValueError(
                        "Rendered dimensions do not match the export request"
                    )
            output.seek(0)
            digest = hashlib.file_digest(output, "sha256").hexdigest()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        return {
            "path": str(destination.resolve()),
            "sha256": digest,
            "dimensions": [width, height],
            "delivery": "awaiting_upload",
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def check_receipt(path, *, sha256, session_id):
    """Return a matching upload receipt, or None while delivery is unconfirmed."""
    try:
        receipt = json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return None
    if not isinstance(receipt, dict) or (
        receipt.get("sha256") != sha256
        or receipt.get("session_id") != session_id
        or receipt.get("object_key") != f"sandboxes/{session_id}/render.png"
        or not receipt.get("uploaded_at")
    ):
        return None
    return receipt

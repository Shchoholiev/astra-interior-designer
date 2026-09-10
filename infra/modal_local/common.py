"""Filesystem and lifecycle primitives shared by Blender and its supervisor."""

import json
import os
import tempfile
import time
from pathlib import Path

ACTIVE_RENDER_STATES = {"queued", "rendering", "image_written"}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def atomic_save(destination, writer):
    """Publish only a complete uncompressed Blender save; retain the old on error."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".save-", dir=destination.parent) as temp:
        pending = Path(temp) / destination.name
        writer(pending)
        with pending.open("rb") as stream:
            if stream.read(7) != b"BLENDER" or pending.stat().st_size < 12:
                raise ValueError("The temporary save is not a complete Blender file")
            os.fsync(stream.fileno())
        os.replace(pending, destination)
    return str(destination)


def classify_health(blender_alive, display_alive, command, render, probe_ok):
    if not blender_alive or not display_alive:
        return "dead"
    if command.get("busy") or render.get("status") in ACTIVE_RENDER_STATES:
        return "busy"
    return "ready" if probe_ok else "unresponsive"


class RenderJob:
    def __init__(self, active_path, report_path, metadata):
        self.active_path = Path(active_path)
        self.report_path = Path(report_path)
        self.started = time.monotonic()
        self.data = {**metadata, "created_at": time.time()}

    def update(self, status, **fields):
        self.data.update(
            status=status,
            updated_at=time.time(),
            elapsed_seconds=round(time.monotonic() - self.started, 3),
            **fields,
        )
        write_json(self.report_path, self.data)
        write_json(self.active_path, self.data)
        return dict(self.data)

    def complete(self, validate_image):
        try:
            fields = validate_image()
            return self.update("completed", **(fields or {}))
        except Exception as exc:
            return self.update("failed", error=str(exc))

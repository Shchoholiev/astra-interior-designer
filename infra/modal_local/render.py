"""Import inside Blender: packed saves, safe loads, and asynchronous Cycles jobs."""

import hashlib
import os
import time
import uuid
from pathlib import Path

import addon_utils
import bpy
from bpy.app.handlers import persistent
from common import (
    ACTIVE_RENDER_STATES,
    RenderJob,
    atomic_save,
    write_json,
)

WORKSPACE = Path(os.environ.get("ASTRA_WORKSPACE", "/workspace"))
STATE = Path(os.environ.get("ASTRA_STATE_DIR", "/run/astra"))
_job = None
_written = False


def configure_optix():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.refresh_devices()
    if not any(device.type == "OPTIX" for device in prefs.devices):
        raise RuntimeError("No OptiX GPU is available")
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.denoising_use_gpu = True
    scene.render.use_persistent_data = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 8
    return [{"name": d.name, "type": d.type, "enabled": d.use} for d in prefs.devices]


def command_state(busy, command=None):
    write_json(
        STATE / "command.json",
        {
            "busy": busy,
            "command": command,
            "pid": os.getpid(),
            "updated_at": time.time(),
        },
    )


def initialize():
    # Blender's enable() unregisters an already-enabled add-on first. Reusing it
    # keeps the current MCP command's socket alive across open_mainfile/load_post.
    if not addon_utils.check("blender_mcp")[1]:
        addon_utils.enable("blender_mcp", default_set=True, persistent=True)
    bpy.context.preferences.addons["blender_mcp"].preferences.telemetry_consent = False
    bpy.context.scene.blendermcp_use_polyhaven = True
    server = bpy.types.blendermcp_server
    if not server.running:
        server.start()
    if server.socket.getsockname()[0] != "127.0.0.1":
        raise RuntimeError("Blender MCP must listen only on loopback")
    if not bpy.app.timers.is_registered(server._drain_command_queue):
        bpy.app.timers.register(server._drain_command_queue, persistent=True)
    if not getattr(server, "_astra_tracked", False):
        execute = server.execute_command

        def tracked(command):
            command_state(True, command.get("type"))
            try:
                return execute(command)
            finally:
                command_state(False)

        server.execute_command = tracked
        server._astra_tracked = True
    devices = configure_optix()
    for handlers, callback in (
        (bpy.app.handlers.load_post, after_load),
        (bpy.app.handlers.render_init, render_started),
        (bpy.app.handlers.render_write, render_written),
        (bpy.app.handlers.render_complete, render_finished),
        (bpy.app.handlers.render_cancel, render_cancelled),
    ):
        if callback not in handlers:
            handlers.append(callback)
    write_json(
        STATE / "blender.json",
        {
            "pid": os.getpid(),
            "blender": bpy.app.version_string,
            "devices": devices,
            "scene": bpy.data.filepath,
            "loaded_at": time.time(),
            "listener": list(server.socket.getsockname()),
        },
    )


@persistent
def after_load(*_):
    global _job
    if _job is not None:
        _job.update("failed", error="Scene changed before render completion")
        _job = None
    initialize()


def save_scene(path=None):
    if bpy.app.is_job_running("RENDER"):
        raise RuntimeError("Wait for rendering before saving the native scene")
    destination = Path(path or WORKSPACE / "scene.blend").resolve()
    bpy.ops.file.pack_all()

    def writer(temporary):
        result = bpy.ops.wm.save_as_mainfile(
            filepath=str(temporary),
            copy=True,
            compress=False,
            relative_remap=False,
        )
        if result != {"FINISHED"}:
            raise RuntimeError(f"Blender save failed: {result}")

    atomic_save(destination, writer)
    return {"path": str(destination), "bytes": destination.stat().st_size}


def open_scene(path):
    if bpy.app.is_job_running("RENDER") or (
        _job and _job.data.get("status") in ACTIVE_RENDER_STATES
    ):
        raise RuntimeError("Wait for rendering before opening another scene")
    source = Path(path).resolve(strict=True)
    result = bpy.ops.wm.open_mainfile(
        filepath=str(source), load_ui=False, use_scripts=False
    )
    if result != {"FINISHED"}:
        raise RuntimeError(f"Cannot open native scene: {source}")
    initialize()
    return {"path": bpy.data.filepath, "objects": len(bpy.context.scene.objects)}


def settings():
    scene = bpy.context.scene
    return {
        "engine": scene.render.engine,
        "backend": "OPTIX",
        "device": scene.cycles.device,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "percentage": scene.render.resolution_percentage,
        "samples": scene.cycles.samples,
        "adaptive_sampling": scene.cycles.use_adaptive_sampling,
        "noise_threshold": scene.cycles.adaptive_threshold,
        "time_limit": scene.cycles.time_limit,
        "denoiser": scene.cycles.denoiser,
        "denoising": scene.cycles.use_denoising,
        "denoising_use_gpu": scene.cycles.denoising_use_gpu,
        "persistent_data": scene.render.use_persistent_data,
        "use_auto_tile": scene.cycles.use_auto_tile,
        "threads_mode": scene.render.threads_mode,
        "threads": scene.render.threads,
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
        "border": scene.render.use_border,
        "crop": scene.render.use_crop_to_border,
        "bounces": {
            "max": scene.cycles.max_bounces,
            "transmission": scene.cycles.transmission_bounces,
            "glossy": scene.cycles.glossy_bounces,
            "transparent": scene.cycles.transparent_max_bounces,
        },
        "format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "color_depth": scene.render.image_settings.color_depth,
        "camera": scene.camera.name if scene.camera else None,
        "camera_matrix": [list(row) for row in scene.camera.matrix_world]
        if scene.camera
        else None,
    }


def queue_render(name="render"):
    global _job, _written
    if bpy.app.is_job_running("RENDER") or (
        _job and _job.data.get("status") in ACTIVE_RENDER_STATES
    ):
        raise RuntimeError("A render is already queued or running")
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Use a simple render name, without a directory")
    configure_optix()
    bpy.context.scene.render.image_settings.file_format = "PNG"
    output = WORKSPACE / "renders" / f"{name}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(output)
    _job = RenderJob(
        STATE / "render.json",
        output.with_name(f"{name}-status.json"),
        {
            "job_id": uuid.uuid4().hex,
            "name": name,
            "filepath": str(output),
            "blender_pid": os.getpid(),
            "settings": settings(),
            "devices": configure_optix(),
        },
    )
    _written = False
    queued = _job.update("queued")

    def begin():
        global _job
        try:
            result = bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)
            if not ({"RUNNING_MODAL", "FINISHED"} & result):
                raise RuntimeError(f"Render did not start: {result}")
        except Exception as exc:
            _job.update("failed", error=str(exc))
            _job = None
        return None

    bpy.app.timers.register(begin, first_interval=0.5)
    return queued


@persistent
def render_started(scene, *_):
    global _job, _written
    _written = False
    if _job is None:
        name = "external-" + uuid.uuid4().hex[:12]
        _job = RenderJob(
            STATE / "render.json",
            WORKSPACE / "renders" / f"{name}-status.json",
            {
                "job_id": name,
                "filepath": bpy.path.abspath(scene.render.filepath),
                "blender_pid": os.getpid(),
                "settings": settings(),
            },
        )
    _job.update("rendering")


@persistent
def render_written(*_):
    global _written
    _written = True
    if _job:
        _job.update("image_written")


@persistent
def render_finished(*_):
    def finalize():
        global _job
        if bpy.app.is_job_running("RENDER"):
            return 0.1
        if _job is None:
            return None
        job, _job = _job, None

        def validate():
            if not _written:
                raise ValueError("Render completed without writing an image")
            path = Path(job.data["filepath"])
            loaded = bpy.data.images.load(str(path), check_existing=False)
            try:
                dimensions = list(loaded.size)
                if not loaded.has_data or not all(dimensions):
                    raise ValueError("Rendered image cannot be decoded")
                loaded.pixels[0]
            finally:
                bpy.data.images.remove(loaded)
            return {
                "dimensions": dimensions,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

        job.complete(validate)
        return None

    bpy.app.timers.register(finalize, first_interval=0.1)


@persistent
def render_cancelled(*_):
    global _job
    if _job:
        _job.update("cancelled")
        _job = None

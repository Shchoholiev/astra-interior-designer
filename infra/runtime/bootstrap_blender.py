"""Configure the pinned Blender MCP add-on and restore the last GLB export."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/astra")
sys.path.insert(0, "/opt/astra/blender-python")

import bpy  # noqa: E402

# Blender's Python is isolated from the container's boto3 installation.
STATE = Path("/run/astra-blender/blender-command.json")


def command_state(busy, command=None):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "busy": busy,
                "command": command,
                "updated_at": time.time(),
            }
        )
    )
    temporary.replace(STATE)


bpy.ops.preferences.addon_enable(module="blender_mcp")
preferences = bpy.context.preferences.addons["blender_mcp"].preferences
preferences.telemetry_consent = False

server = bpy.types.blendermcp_server
assert server.host in {"localhost", "127.0.0.1"}
assert server.running
execute = server.execute_command


def tracked_command(command):
    command_state(True, command.get("type"))
    try:
        return execute(command)
    finally:
        command_state(False)


server.execute_command = tracked_command
command_state(True, "restore")
try:
    scene_path = Path("/workspace/scene.glb")
    if scene_path.is_file():
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(scene_path))

    cycles = bpy.context.preferences.addons["cycles"].preferences
    cycles.compute_device_type = "OPTIX"
    cycles.refresh_devices()
    assert any(device.type == "OPTIX" for device in cycles.devices), "No OptiX GPU"
    for device in cycles.devices:
        device.use = device.type == "OPTIX"
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.device = "GPU"
finally:
    command_state(False)

print(
    "ASTRA_BLENDER_STARTED " + json.dumps({"blender": bpy.app.version_string}),
    flush=True,
)

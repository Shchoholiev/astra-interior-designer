"""Initialize the tested Blender tools under the backend's unprivileged runtime."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/astra/local")
sys.path.insert(0, "/opt/astra/blender-python")

import bpy  # noqa: E402
import render  # noqa: E402

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


# Reuse the existing supervisor's command marker, including after native loads.
render.command_state = command_state
(render.STATE / "render.json").unlink(missing_ok=True)
for name in ("assets", "scripts", "renders", "logs"):
    (Path("/workspace") / name).mkdir(exist_ok=True)
command_state(True, "restore")
try:
    native_path = Path("/workspace/scene.blend")
    scene_path = Path("/workspace/scene.glb")
    if native_path.is_file():
        render.open_scene(native_path)
    else:
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        if scene_path.is_file():
            bpy.ops.import_scene.gltf(filepath=str(scene_path))
        render.initialize()
finally:
    command_state(False)

print(
    "ASTRA_BLENDER_STARTED " + json.dumps({"blender": bpy.app.version_string}),
    flush=True,
)

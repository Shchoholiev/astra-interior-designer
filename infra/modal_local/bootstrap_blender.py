"""Bootstrap one persistent Blender process without running embedded scene scripts."""

import sys
from pathlib import Path

sys.path.insert(0, "/opt/astra/local")
sys.path.insert(0, "/opt/astra/blender-python")

import bpy  # noqa: E402
import render  # noqa: E402

scene = Path("/workspace/scene.blend")
if scene.exists():
    render.open_scene(scene)
else:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    render.initialize()
render.command_state(False)
print("ASTRA_BLENDER_BOOTSTRAPPED", flush=True)

"""Validate installed tooling with a scene generated only inside test sandboxes."""

import argparse
import asyncio
import base64
import hashlib
import json
import subprocess
import time
from pathlib import Path

from common import read_json, write_json
from mcp_client import call, code, connect, evaluate
from PIL import Image

ROOT = Path("/workspace")
SMOKE_SCENE = """
import bpy
from mathutils import Vector
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, location=(0,0,1))
sphere = bpy.context.object
sphere.name = 'Smoke sphere'
material = bpy.data.materials.new('Smoke material')
material.use_nodes = True
image = bpy.data.images.new('Smoke texture', width=32, height=32)
image.generated_type = 'COLOR_GRID'
# Generated images are embedded differently; save a runtime PNG to exercise packing.
image.filepath_raw = '/workspace/assets/smoke-texture.png'
image.file_format = 'PNG'
image.save()
image.pack()
texture = material.node_tree.nodes.new('ShaderNodeTexImage')
texture.image = image
bsdf = material.node_tree.nodes.get('Principled BSDF')
material.node_tree.links.new(texture.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = .25
sphere.data.materials.append(material)
bpy.ops.mesh.primitive_plane_add(size=200)
bpy.ops.object.light_add(type='AREA', location=(2,-3,6))
bpy.context.object.data.energy = 1500
bpy.context.object.data.shape = 'DISK'
bpy.context.object.data.size = 4
bpy.ops.object.camera_add(location=(5,-7,4))
camera = bpy.context.object
camera.name = 'Smoke camera'
direction = Vector((0,0,1))-camera.location
camera.rotation_euler = direction.to_track_quat('-Z','Y').to_euler()
scene = bpy.context.scene
scene.camera = camera
scene.render.resolution_x, scene.render.resolution_y = 1536, 1024
scene.render.resolution_percentage = 100
scene.cycles.samples = 128
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = .01
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.render.image_settings.color_mode = 'RGB'
"""
SIGNATURE = """(lambda bpy: {
    'camera': [list(row) for row in bpy.context.scene.camera.matrix_world],
    'shader_links': sorted([
        link.from_node.name, link.from_socket.name,
        link.to_node.name, link.to_socket.name
    ] for link in bpy.data.materials['Smoke material'].node_tree.links),
    'packed_image': bool(bpy.data.images['Smoke texture'].packed_file),
})(__import__('bpy'))"""


def image_report(path):
    with Image.open(path) as image:
        image.load()
        assert image.format == "PNG"
        size = list(image.size)
    return {
        "dimensions": size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def health():
    result = subprocess.run(
        ["python", "/opt/astra/local/boot.py", "health"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


async def screenshot(client, path):
    result, _ = await call(client, "get_viewport_screenshot", max_size=1000)
    images = [item for item in result.content if item.type == "image"]
    assert images, "No MCP viewport image"
    path.write_bytes(base64.b64decode(images[0].data))
    return image_report(path)


async def verify(args):
    report = {
        "name": args.name,
        "started_at": time.time(),
        "status": "running",
        "agent_session": {
            "status": "unverified",
            "reason": "No Agents API turn submitted",
        },
        "asset_import": "not_requested",
    }
    try:
        assert not Path("/opt/astra/fixtures").exists()
        assert not (ROOT / "scene.blend").exists()
        report["no_packaged_scene"] = True
        report["versions"] = read_json("/opt/astra/local/versions.json")
        async with connect() as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            required = {
                "get_scene_info",
                "get_object_info",
                "get_viewport_screenshot",
                "execute_blender_code",
                "get_addon_status",
                "get_polyhaven_status",
                "get_polyhaven_categories",
                "search_polyhaven_assets",
                "download_polyhaven_asset",
                "set_texture",
            }
            assert required <= tools, required - tools
            report["tools"] = sorted(tools)
            _, status = await call(client, "get_addon_status")
            report["addon"] = json.loads(status)
            assert report["addon"]["protocol_version"] == 5
            assert report["addon"]["telemetry_consent"] is False
            await call(client, "get_scene_info")
            assert (
                await evaluate(client, "len(__import__('bpy').context.scene.objects)")
                == 0
            )
            report["initial_health"] = health()
            blender_pid = report["initial_health"]["pids"]["blender"]
            await code(
                client,
                f"import bpy; o=bpy.data.objects.new({args.name!r},None); "
                "bpy.context.collection.objects.link(o)",
            )
            assert await evaluate(
                client, f"{args.name!r} in __import__('bpy').data.objects"
            )
            (ROOT / f"{args.name}.txt").write_text(args.name)
            report["persistent_scene"] = True
            report["viewport"] = await screenshot(
                client, ROOT / "renders/factory-viewport.png"
            )
            print("MCP_PERSISTENCE_PASSED", flush=True)
            if args.isolation_only:
                report["status"] = "passed"
                return

            await code(client, SMOKE_SCENE)
            before = await evaluate(client, SIGNATURE)
            assert before["packed_image"]
            started = time.monotonic()
            queued = await evaluate(client, "render.queue_render('smoke')")
            report["queue_call_seconds"] = round(time.monotonic() - started, 3)
            assert queued["status"] == "queued"
            report["busy_health"] = health()
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                render = read_json(ROOT / "renders/smoke-status.json")
                if render.get("status") in {"completed", "failed", "cancelled"}:
                    break
                assert report["busy_health"]["blender_state"] == "busy"
                await asyncio.sleep(0.25)
            else:
                raise TimeoutError("Smoke render exceeded 300 seconds")
            assert render["status"] == "completed", render
            report["render"] = render
            report["image"] = image_report(ROOT / "renders/smoke.png")
            assert report["image"]["dimensions"] == [1536, 1024]
            assert render["settings"]["samples"] == 128
            assert render["settings"]["camera"] == "Smoke camera"
            assert render["settings"]["denoising_use_gpu"]
            assert report["image"]["sha256"] == render["sha256"]
            assert health()["pids"]["blender"] == blender_pid
            await call(client, "get_scene_info")
            report["render_viewport"] = await screenshot(
                client, ROOT / "renders/smoke-viewport.png"
            )
            print("GPU_RENDER_PASSED", flush=True)

            await code(
                client,
                f"import bpy; o=bpy.data.objects.new({args.name!r},None); "
                "o.location=(1,2,3); o['acceptance_edit']='survives-reopen'; "
                "bpy.context.collection.objects.link(o)",
            )
            report["save"] = await evaluate(client, "render.save_scene()")
            (ROOT / "assets/smoke-texture.png").unlink()
            await evaluate(client, "render.open_scene('/workspace/scene.blend')")
            assert await evaluate(client, SIGNATURE) == before
            assert await evaluate(
                client, f"list(__import__('bpy').data.objects[{args.name!r}].location)"
            ) == [1.0, 2.0, 3.0]
            assert (
                await evaluate(
                    client,
                    f"__import__('bpy').data.objects[{args.name!r}]['acceptance_edit']",
                )
                == "survives-reopen"
            )
            assert health()["pids"]["blender"] == blender_pid
            report["native_save_reopen"] = "passed"
            print("NATIVE_SAVE_REOPEN_PASSED", flush=True)

            if args.check_assets:
                _, enabled = await call(client, "get_polyhaven_status")
                assert "enabled" in enabled.lower()
                await call(client, "get_polyhaven_categories", asset_type="models")
                _, found = await call(
                    client,
                    "search_polyhaven_assets",
                    asset_type="models",
                    categories="food",
                )
                assert "Found" in found
                await code(
                    client,
                    "import bpy; bpy.context.window.scene="
                    "bpy.data.scenes.new('Asset acceptance'); render.initialize()",
                )
                _, imported = await call(
                    client,
                    "download_polyhaven_asset",
                    asset_id="food_apple_01",
                    asset_type="models",
                    resolution="1k",
                    file_format="gltf",
                )
                assert "imported" in imported.lower(), imported
                report["asset_viewport"] = await screenshot(
                    client, ROOT / "renders/asset-viewport.png"
                )
                await evaluate(
                    client,
                    "render.save_scene('/workspace/assets/polyhaven-apple.blend')",
                )
                provenance = {
                    "asset_id": "food_apple_01",
                    "source": "https://polyhaven.com/a/food_apple_01",
                    "license": "CC0",
                    "downloaded_via": "blender-mcp",
                }
                write_json(ROOT / "assets/polyhaven-apple.json", provenance)
                report["asset_import"] = provenance
                await evaluate(client, "render.open_scene('/workspace/scene.blend')")
            report["final_health"] = health()
            assert report["final_health"]["pids"]["blender"] == blender_pid

        async with connect() as replacement:
            assert await evaluate(
                replacement, f"{args.name!r} in __import__('bpy').data.objects"
            )
        report["mcp_client_restart"] = "passed"
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        raise
    finally:
        report["finished_at"] = time.time()
        write_json(ROOT / "renders/acceptance.json", report)
        print(
            "ACCEPTANCE_RESULT "
            + json.dumps({"status": report["status"], "error": report.get("error")}),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="probe-a")
    parser.add_argument("--isolation-only", action="store_true")
    parser.add_argument("--check-assets", action="store_true")
    asyncio.run(verify(parser.parse_args()))

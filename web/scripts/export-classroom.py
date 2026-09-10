"""Prepare Blender's CC0 Classroom demo for fast web GLB playback."""

from pathlib import Path

import bpy


OUTPUT = Path(__file__).resolve().parents[1] / "public" / "models" / "classroom.glb"
SOURCE = Path(bpy.data.filepath).parent

# The source contains three render-compositing scenes. Only the furnished main
# scene is useful to the interactive viewer.
bpy.context.window.scene = bpy.data.scenes["_mainScene"]


def material_color(name: str) -> tuple[float, float, float, float]:
    """Give legacy Cycles materials a useful web-PBR base color."""
    key = name.lower()
    if "blackboard" in key:
        return (0.025, 0.075, 0.055, 1)
    if "black" in key or "carbon" in key:
        return (0.025, 0.03, 0.028, 1)
    if "wood" in key or "cork" in key:
        return (0.34, 0.15, 0.055, 1)
    if "leather" in key:
        return (0.22, 0.075, 0.035, 1)
    if "brass" in key or "gold" in key:
        return (0.55, 0.31, 0.07, 1)
    if "metal" in key or "blade" in key:
        return (0.23, 0.27, 0.28, 1)
    if "wall" in key or "plaster" in key or "beige" in key:
        return (0.72, 0.63, 0.49, 1)
    if "paper" in key or "chalk" in key or "ceiling" in key or "white" in key:
        return (0.83, 0.82, 0.75, 1)
    if "plastic" in key:
        return (0.12, 0.25, 0.18, 1)
    if "drawing" in key or "pencil" in key or "postit" in key:
        palette = ((0.62, 0.18, 0.10, 1), (0.12, 0.34, 0.54, 1), (0.73, 0.55, 0.10, 1))
        return palette[sum(map(ord, key)) % len(palette)]
    return (0.46, 0.43, 0.36, 1)


texture_rules = {
    "woodfloor": SOURCE / "textures/_baseTextures/base_woodFloor.jpg",
    "blackboard": SOURCE / "textures/blackBoard.png",
    "woodplanks": SOURCE / "textures/woodPlanks.jpg",
    "cork": SOURCE / "textures/cork.jpg",
    "worldmap": SOURCE / "textures/europeMap.png",
}

# The 2019 source predates glTF-compatible Principled materials. Rebuild its
# materials so the detailed downloaded geometry is lit correctly in Three.js.
for material in list(bpy.data.materials):
    material = material.make_local()
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = material_color(material.name)
    shader.inputs["Metallic"].default_value = 0.65 if any(
        word in material.name.lower() for word in ("metal", "brass", "blade")
    ) else 0.0
    shader.inputs["Roughness"].default_value = 0.56
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    material_key = material.name.lower().replace("_", "")
    for keyword, texture_path in texture_rules.items():
        if keyword in material_key and texture_path.exists():
            image = bpy.data.images.load(str(texture_path), check_existing=True)
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = image
            material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
            break

# Resize oversized source textures before embedding them. This keeps the demo
# detailed while avoiding a production-sized network payload.
for image in bpy.data.images:
    if image.source == "FILE" and max(image.size) > 1024:
        width, height = image.size
        scale = 1024 / max(width, height)
        image.scale(max(1, round(width * scale)), max(1, round(height * scale)))

# Browser lighting is supplied by Three.js. Exporting the Cycles light rig and
# render cameras only increases file size and can alter the preview.
for scene_object in list(bpy.context.scene.objects):
    materials = getattr(scene_object.data, "materials", ()) if scene_object.data else ()
    is_render_helper = any(
        material and ("portal" in material.name.lower() or material.name == "blackBoardLight")
        for material in materials
    )
    if scene_object.type in {"LIGHT", "CAMERA"} or is_render_helper:
        bpy.data.objects.remove(scene_object, do_unlink=True)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=str(OUTPUT),
    export_format="GLB",
    export_apply=True,
    export_cameras=False,
    export_lights=False,
    export_image_format="AUTO",
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=6,
)

print(f"Exported {OUTPUT} ({OUTPUT.stat().st_size / 1024 / 1024:.1f} MB)")

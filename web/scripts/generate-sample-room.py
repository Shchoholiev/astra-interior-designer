import bpy
from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "public" / "models" / "sample-room.glb"


def material(name, color, roughness=0.75, metallic=0.0):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.roughness = roughness
    value.metallic = metallic
    return value


def box(name, location, scale, mat, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = tuple(value / 2 for value in scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("Soft edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    obj.data.materials.append(mat)
    return obj


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

oak = material("Oak", (0.52, 0.29, 0.14), 0.72)
plaster = material("Warm plaster", (0.86, 0.81, 0.72), 0.95)
green = material("Forest linen", (0.18, 0.27, 0.22), 0.92)
green_dark = material("Forest linen shadow", (0.12, 0.20, 0.16), 0.92)
terracotta = material("Terracotta rug", (0.45, 0.14, 0.08), 0.98)
walnut = material("Walnut", (0.25, 0.12, 0.05), 0.68)
linen = material("Natural linen", (0.67, 0.52, 0.34), 0.96)
ceramic = material("Ceramic", (0.36, 0.12, 0.07), 0.8)
leaves = material("Leaves", (0.12, 0.29, 0.12), 0.9)
glass = material("Window glass", (0.28, 0.48, 0.58), 0.22, 0.05)

box("Floor", (0, 0, -0.08), (8, 6, 0.16), oak, 0)
box("Back wall", (0, -3, 1.5), (8, 0.12, 3), plaster, 0)
box("Left wall", (-4, 0, 1.5), (0.12, 6, 3), plaster, 0)
box("Right wall", (4, 0, 1.5), (0.12, 6, 3), plaster, 0)
box("Rug", (0, 0.45, 0.025), (3.8, 2.5, 0.05), terracotta, 0.02)

box("Sofa seat", (0, -1.65, 0.52), (3.4, 0.82, 0.62), green, 0.12)
box("Sofa back", (0, -1.96, 1.02), (3.4, 0.25, 0.8), green_dark, 0.1)
box("Sofa arm L", (-1.66, -1.65, 0.8), (0.26, 0.86, 0.82), green_dark, 0.1)
box("Sofa arm R", (1.66, -1.65, 0.8), (0.26, 0.86, 0.82), green_dark, 0.1)
box("Coffee table", (0, 0.4, 0.39), (1.95, 0.92, 0.12), walnut, 0.05)
for x in (-0.78, 0.78):
    for y in (0.12, 0.68):
        box("Table leg", (x, y, 0.2), (0.09, 0.09, 0.4), walnut, 0.025)

box("Chair seat", (-2.65, 1.72, 0.52), (1.18, 1.05, 0.18), linen, 0.1)
box("Chair back", (-2.65, 2.12, 1.0), (1.18, 0.2, 0.82), linen, 0.1)
box("Window", (0, -2.925, 1.85), (2.35, 0.025, 1.4), glass, 0)
box("Window frame H", (0, -2.9, 1.85), (2.45, 0.08, 0.07), walnut, 0)
box("Window frame V", (0, -2.9, 1.85), (0.07, 0.08, 1.5), walnut, 0)

bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.62, depth=1.15, location=(2.7, 1.65, 0.58))
bpy.context.object.data.materials.append(ceramic)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.72, location=(2.7, 1.65, 1.48))
bpy.context.object.data.materials.append(leaves)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB", export_yup=True, export_apply=True)
print(OUTPUT)

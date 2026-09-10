"""Import inside Blender to configure a verified, centered Three.js perspective."""

import hashlib
import json
import math
import re
import struct
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

STANDARD_GLTF_TO_BLENDER = (
    (1, 0, 0, 0),
    (0, 0, -1, 0),
    (0, 1, 0, 0),
    (0, 0, 0, 1),
)


def parse_context(message):
    def field(label):
        values = re.findall(rf"^{re.escape(label)}:\s*([^\n]+)$", message, re.M)
        if len(values) != 1:
            raise ValueError(f"Expected exactly one {label} field")
        return values[0].strip()

    return {
        "scene_version": field("Scene version"),
        "position": json.loads(field("Position")),
        "quaternion_xyzw": json.loads(field("Rotation quaternion (x, y, z, w)")),
        "vertical_fov_degrees": float(field("Vertical field of view")),
        "aspect_ratio": float(field("Aspect ratio")),
        "coordinate_space": field("Coordinate space"),
    }


def _finite(values, length, label):
    if len(values) != length or not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in values
    ):
        raise ValueError(f"{label} must contain {length} finite numbers")
    return tuple(values)


def verify_scene_version(glb_path, version):
    expected = version.removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Resolve the scene version to the displayed GLB's SHA-256")
    with Path(glb_path).open("rb") as source:
        header = source.read(12)
        if len(header) != 12 or struct.unpack("<4sII", header)[:2] != (b"glTF", 2):
            raise ValueError("Scene version must identify a GLB 2 file")
        source.seek(0)
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(
            "Scene version mismatch; use its checkpoint or refreshed context"
        )
    return digest


def _basis(rows):
    if len(rows) != 4:
        raise ValueError("viewer_to_blender must be a 4x4 matrix of rows")
    matrix = Matrix([_finite(row, 4, "Matrix row") for row in rows])
    if any(abs(matrix[3][i] - (1 if i == 3 else 0)) > 1e-7 for i in range(4)):
        raise ValueError("viewer_to_blender must be affine")
    axes = [matrix.to_3x3().col[i] for i in range(3)]
    scales = [axis.length for axis in axes]
    scale = sum(scales) / 3
    if scale <= 0 or matrix.to_3x3().determinant() <= 0:
        raise ValueError("viewer_to_blender must have positive uniform scale")
    if max(abs(size / scale - 1) for size in scales) > 1e-5 or any(
        abs(axes[i].dot(axes[j])) > scale * scale * 1e-5
        for i in range(3)
        for j in range(i)
    ):
        raise ValueError("Nonuniform scale or shear needs a full projection mapping")
    return matrix


def configure_camera(
    scene,
    context,
    *,
    glb_path,
    width,
    height,
    viewer_to_blender=STANDARD_GLTF_TO_BLENDER,
    name="Viewer export camera",
):
    """Validate before mutation; retain the scene's original camera object."""
    if bpy.app.is_job_running("RENDER"):
        raise RuntimeError("Wait for the active render before configuring a camera")
    digest = verify_scene_version(glb_path, context["scene_version"])
    if context["coordinate_space"] != "Three.js viewer world":
        raise ValueError("Expected Three.js viewer world coordinates")
    position = Vector(_finite(context["position"], 3, "Position"))
    x, y, z, w = _finite(context["quaternion_xyzw"], 4, "Quaternion")
    rotation = Quaternion((w, x, y, z))
    if abs(rotation.magnitude - 1) > 1e-3:
        raise ValueError("Expected a unit world quaternion in x,y,z,w order")
    rotation.normalize()
    fov, aspect = _finite(
        (context["vertical_fov_degrees"], context["aspect_ratio"]), 2, "FOV/aspect"
    )
    if not 0 < fov < 180 or aspect <= 0:
        raise ValueError("Expected 0 < vertical FOV < 180 and a positive aspect")
    if any(type(size) is not int or not 4 <= size <= 65536 for size in (width, height)):
        raise ValueError("Width and height must be integer Blender pixel dimensions")
    # Permit rounding the short edge to the nearest pixel, but no crop/stretch.
    short_error = (
        abs(height - width / aspect) if aspect >= 1 else abs(width - height * aspect)
    )
    if short_error > 0.500001:
        raise ValueError("Output dimensions conflict with the viewer aspect ratio")
    basis = _basis(viewer_to_blender)
    lens = 24 / (2 * math.tan(math.radians(fov) / 2))
    lens_property = bpy.types.Camera.bl_rna.properties["lens"]
    if not lens_property.hard_min <= lens <= lens_property.hard_max:
        raise ValueError("Requested FOV exceeds Blender's perspective lens range")

    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    camera.rotation_mode = "QUATERNION"
    camera.location = basis @ position
    camera.rotation_quaternion = basis.to_quaternion() @ rotation
    data.type = "PERSP"
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24
    data.lens = lens
    data.shift_x = data.shift_y = 0
    data.dof.use_dof = False
    previous_camera = scene.camera.name if scene.camera else None
    # Keep existing clip distances; clipping is not specified in the message.
    if scene.camera:
        data.clip_start = scene.camera.data.clip_start
        data.clip_end = scene.camera.data.clip_end
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.use_border = scene.render.use_crop_to_border = False
    scene.render.use_multiview = False
    for layer in scene.view_layers:
        layer.update()
    return {
        "scene_version": digest,
        "camera": camera.name,
        "previous_camera": previous_camera,
        "viewer_context": context,
        "viewer_to_blender_rows": [list(row) for row in basis],
        "camera_matrix_world": [list(row) for row in camera.matrix_world],
        "resolution": [width, height],
        "vertical_fov_degrees": math.degrees(
            2 * math.atan(data.sensor_height / (2 * data.lens))
        ),
        "pixel_aspect": [scene.render.pixel_aspect_x, scene.render.pixel_aspect_y],
        "dimension_rounding_pixels": short_error,
    }

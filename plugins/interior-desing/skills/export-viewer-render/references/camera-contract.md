# Viewer camera contract

Supported input is a centered perspective camera with square pixels, no
`filmOffset`, no `setViewOffset` crop, and no custom projection matrix. The message
contains effective vertical FOV, so zoom must not be applied again. If the viewer
uses an asymmetric or orthographic projection, request its full projection
contract; the fields below cannot encode it exactly.

Near/far clipping is also absent from the message. The helper retains the native
camera's clip distances. If the viewer intentionally clips visible geometry,
obtain its near/far planes and convert their distances using the established
world scale before claiming identical visibility.

```text
Viewer camera context for this render:
Scene version: <SHA-256 of displayed GLB bytes>
Position: [x, y, z]
Rotation quaternion (x, y, z, w): [qx, qy, qz, qw]
Vertical field of view: <degrees, including zoom>
Aspect ratio: <width / height>
Coordinate space: Three.js viewer world

Render from this viewpoint. Convert the camera into Blender's
scene coordinates, preserve the framing, and deliver the image.
```

The frontend must update camera world/projection matrices, take position and
quaternion using `getWorldPosition` / `getWorldQuaternion`, and take FOV using
`getEffectiveFOV()`. Capture all fields and the displayed scene version together.
Local camera position/quaternion are insufficient when the camera has a parent.
The scene hash identifies downloaded GLB bytes, not a URL whose query may change.

For an unchanged, unscaled Blender export with standard glTF Y-up conversion and
the viewer displaying it at original origin/scale, define:

```text
B = [[1, 0,  0, 0],
     [0, 0, -1, 0],
     [0, 1,  0, 0],
     [0, 0,  0, 1]]
position_blender = B @ position_viewer
rotation_blender = quaternion(B) @ quaternion_viewer
```

Three.js quaternions are `(x,y,z,w)`; Blender's constructor takes `(w,x,y,z)`.
Both cameras look along their own local `-Z` with local `+Y` up. Convert the world
pose by **premultiplication**. Do not use object rotation basis conjugation
`B @ R @ inverse(B)` as the final camera rotation: that introduces another local
camera-axis correction and changes the view.

For a different verified pipeline, let `E` map native Blender world to the
exported GLB and `V` map that GLB to viewer world. Supply
`viewer_to_blender = inverse(E) @ inverse(V)` to the helper. Its matrices are
**nested rows**, unlike flat Three.js `Matrix4.elements` arrays, which are column
major. Transpose/reassemble those arrays explicitly. The helper supports positive
uniform scale, translation, and rotation; reflection, shear, or nonuniform scale
needs a fuller projection treatment and is rejected. Do not guess `V` from room
size. Unit conversion comes from the actual export/import path, not merely the
current Blender unit label.

Use `sensor_fit='VERTICAL'` and `lens = sensor_height / (2*tan(vfov/2))`.
`camera.data.angle` with automatic sensor fit can describe the wrong axis,
particularly after changing aspect. Verify actual projection at final resolution.
Pixel positions can differ by the documented nearest-integer dimension rounding;
do not call a larger discrepancy a rounding error.

Sources: [Three.js perspective camera](https://threejs.org/docs/pages/PerspectiveCamera.html),
[camera forward axis](https://threejs.org/docs/pages/Camera.html),
[Blender camera properties](https://docs.blender.org/api/5.3/bpy.types.Camera.html),
[Blender glTF basis and camera correction](https://github.com/blender/blender/blob/main/scripts/addons_core/io_scene_gltf2/blender/imp/blender_gltf.py).

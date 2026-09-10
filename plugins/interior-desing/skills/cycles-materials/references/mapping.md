# Mapping and texture checks

Use this reference when creating image-based materials, repairing imported shaders, or investigating a seam or scale problem. Check the connected path used by the target surface, including nested groups and material overrides when present.

## Image meaning and availability

Inspect the provider's manifest, source graph, or channel preview before connecting packed maps. For glTF metallic-roughness textures, roughness is green and metallic is blue; other texture packs can differ. Preserve an occlusion channel separately rather than treating the entire RGB image as roughness.

Use the source's declared color encoding for color images, commonly sRGB for base-color PNG/JPEG textures. Roughness, metallic, normals, height, and masks are data and normally use Non-Color. A separate image datablock is needed when one file must be interpreted differently in different materials. Preserve HDR/EXR encoding according to the source rather than assigning sRGB to every image.

Distinguish a missing file from an unloaded image buffer. After a GPU render, `image.has_data == False` alone does not establish a missing texture. Check packed storage or the resolved local source and attempt a small pixel read/decode. Reload an external image only when its source is available and doing so will not discard unsaved image edits. Resolve linked-library paths relative to their library; enumerate tiles for UDIM images rather than checking a literal `<UDIM>` filename.

## A UV edit that does not affect the render

Trace each Image Texture's Vector input. A named UV Map node selects that named layer; an implicit UV input or Texture Coordinate UV output uses the render-active layer. The layer selected for editing can be different. Inspect both selections and the actual shader connection before another UV edit. [Blender UV Map documentation](https://docs.blender.org/manual/en/5.2/render/shader_nodes/input/uv_map.html)

When selecting a dedicated surface UV:

1. Preserve other objects' mapping by isolating shared data that will change.
2. Create or reuse the intended named layer on every mesh receiving this mapping.
3. Connect a named UV Map node consistently to the related color, roughness, normal, and height image vectors. Preserve intentional alternate mappings such as a separate detail layer.
4. Point each tangent-space Normal Map node at the UV layer used by its own image. Update the render-active layer only if implicit consumers should also use it; inspect other materials on that mesh first.

Tangent-space normal maps need matching texture coordinates and tangent UVs. Check OpenGL versus DirectX convention, use Non-Color, and inspect the running version's convention controls before inserting a green-channel inversion. [Blender Normal Map documentation](https://docs.blender.org/manual/en/latest/render/shader_nodes/displacement/normal_map.html)

## A seam that is inside the source image

Inspect color and data maps directly. Tile scans may contain grout, baked shading, or repeating joints. UV selection cannot remove a line embedded in a sampled region.

Prefer a continuous slab source for a slab. A grout-free crop is usable when it retains sufficient resolution, coherent grain proportions, and matching coordinates across the map set. Derive the bounds from that image; do not reuse coordinates from a previous scene. Inspect top faces, edges, and corners so a planar top mapping does not stretch the slab sides.

## Physical scale and surface detail

Calculate physical dimensions from object dimensions and scene unit scale; inspect unapplied transforms. Treat photographic dimensions as estimates if no measurements exist. Define repeat coverage in physical units before choosing UV scale. Preserve the source image's aspect ratio and intended anisotropy.

Generated coordinates normalize each object's bounds, so identical settings can yield different grain sizes on different objects. Explicit UV coverage or a controlled coordinate object gives predictable local mapping. World-position detail is useful for stationary architectural surfaces when its scale accounts for scene units; moving objects through it can make the texture slide.

Keep atlas normals that describe folds and seams. Add finer relief only when visible at the output scale. For a height-detail layer, a Bump node can take the existing normal as its base. Combining two normal maps requires a proper normal-blending method in a consistent space; adding RGB colors is not equivalent. Inspect grazing highlights for inverted relief, oversized pores, and shimmer before increasing strength.

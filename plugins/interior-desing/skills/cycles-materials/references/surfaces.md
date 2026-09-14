# Surface guidance

Read only the relevant material family. Treat parameter choices as hypotheses to check in the actual scene; finishes, texture conventions, dimensions, and viewing distance differ.

## Leather and upholstery

Evaluate three scales separately: the overall upholstered form, localized folds at joins or bends, and fine grain or pores. Read [furniture construction](../../build-interior-scene/references/furniture-construction.md) when silhouette, cushion thickness, or seam placement is wrong. Keep a material-only correction within scope; amplifying bump does not repair those shapes.

Start with the imported atlas and normal map when they contain seams, stitching, and folds. Correct packed-map channels and color spaces before adjusting roughness. A smooth bright highlight can come from the coat layer even when base roughness appears high; inspect both contributions.

Match the finish visible in the reference: smooth or pebbled leather, suede, fabric, and coated leather have different appearances. A high-resolution scan can still be the wrong finish. If the source reads as fibers or directional grain instead of the intended leather, inspect the source and mapping before further roughness tuning. Preserve useful authored detail when suitable; choose a better source or calibrated procedural finish when it cannot fit the target.

For a soft leather finish, preserve roughness variation and broaden highlights without erasing the material's sheen. Use coat when the intended leather has a coating; reducing it everywhere would also remove legitimate patent or lacquered finishes. Recolor through the useful atlas detail rather than replacing the entire base color with a flat constant. Fine pore relief should read as a surface texture, not large dents.

Control grain width separately from relief depth. Use coherent physical coverage across the seat, back, and side panels, with aligned color, roughness, and normal detail as described in [mapping checks](mapping.md). Keep larger folds localized to the demonstrated construction and taper them into the surrounding surface; uniform ripples or deep pore relief can make firm leather read as damaged or plush. Check grazing highlights in a close-up and detail survival in the room render after denoising. Values that worked on one chair are not universal leather settings.

For fabric, use the weave direction and a restrained fiber response. Sheen can represent fine fibers, while coat represents a coating; they solve different appearance problems. [Blender Principled BSDF layer documentation](https://docs.blender.org/manual/sr/5.2/render/shader_nodes/shader/principled.html)

If the cushion lacks thickness, soft edges, or folds in silhouette, report the geometry limitation. Material noise cannot supply those shapes.

## Lampshade fabric

For a lit textile shade, check the actual shell and its modifiers before tuning the shader. A thin-sheet scattering approximation applied to both sides of a Solidify shell can attenuate light twice. Use one deliberate layer for that approximation, or model the real layered construction with a material appropriate to its thickness; do not remove a genuine lining merely to brighten the shade.

Use diffuse transmission, such as a native Translucent BSDF mixed with the fabric surface, to represent light scattered through thin cloth. Clear-glass transmission and uniformly emissive fabric do not reproduce the same appearance. Inspect weave scale and restrained density variation in a completed lit preview, retaining visible top/bottom rims and plausible brightness variation without coarse mottling. If the shade stays dark, check the bulb and source placement using [practical fixture guidance](../../light-and-render-interior/references/photographic-lighting.md) before increasing transmission or light power.

## Wood and veneer

Align grain with each panel's construction and preserve a believable grain width across objects of different sizes. A cabinet door, end grain, and a curved counter edge can need different mapping. Match satin, oiled, or polished response to the reference before adding wear.

Keep wood color variation and use roughness variation to break up reflections. Restrict bumps to plausible pore relief. Check veneer transitions and edge treatments in the render; stronger normal maps will not repair an incorrect grain direction.

### Texture scale and repetition on connected furniture parts

Distinguish object proportions, texture aspect distortion, and texture feature size. Inspect the referenced region, transforms, UV extents, and connected mapping first. Keep approved geometry fixed for a texture correction; changing dimensions requires a separately demonstrated geometry defect within the user's scope.

Choose a common visible grain width for parts intended to share one wood or veneer finish. Match direction to construction, such as planar grain on a tabletop, vertical grain on a support, and grain following an edge band. Fitting the complete image independently to each part's bounds makes feature size depend on its shape; the same source file does not ensure matching wood scale.

Control repetition along the grain separately from cross-grain width. Increasing just one mapping axis can squash the source features; uniformly shrinking the entire image into every repeat can make the grain too fine beside neighboring parts. Choose a repeatable source region or authored seamless texture, and repeat that region along the support at the intended physical scale while preserving feature proportions. Numeric repeat counts and coverage values are specific to the source and furniture, not universal defaults.

Keep the related color, roughness, normal, and displacement maps on the same coordinates, crop, and repetition. Preserve intentionally separate detail layers. Follow [mapping checks](mapping.md) for tangent-space normal UVs; inspect mirrored regions for correct directional relief rather than blindly mirroring maps or inverting a normal channel. Check repeat joins and conspicuous duplicated features.

Compare all connected parts together in matching before/after close-ups and the final room framing, with geometry, camera, lighting, and exposure held constant. Judge grain width, direction, contrast, finish, seams, and detail survival after denoising. Successful node checks alone cannot establish that the parts read as the same material.

## Stone, tile, and plaster

Distinguish a continuous slab from assembled tiles. Choose mapping and source imagery accordingly; inspect the data maps as well as the color for baked joints. Vein scale and aspect ratio should fit the object's dimensions.

Polished, honed, and rough stone need different reflection spread and relief. Match the finish without adding a gloss coat by default. Treat plaster grain as shallow relief at physical scale; conspicuous pits or high-frequency noise can make a smooth wall read as foam.

## Glass and liquids

Inspect mesh thickness, normals, overlapping surfaces, and the actual occupied volume before changing the shader. For optical glass, use a native reflective/transmissive surface with a plausible IOR; low alpha or an arbitrary transparent mix is not a substitute for refraction.

Match the shading model to the geometry: a closed shell with inner and outer surfaces needs coherent solid-glass interfaces, while a thin-sheet approximation serves a different representation. Do not apply a thin-surface shortcut merely because the modeled wall is physically thin. Inspect evaluated normals at rims, stems, and profile creases; inappropriate smoothing can distort refraction even when the mesh is closed. Preserve intended smooth curves and deliberate profile transitions instead of marking every edge sharp.

Ordinary clear glass often starts near IOR 1.5 and water near 1.33, with values refined for the intended material. Use depth-dependent absorption for colored glass or liquid where an enclosed volume supports it. Calibrate density to scene scale and thickness; a density copied from another scene can turn a bottle opaque. Keep the container and liquid interfaces coherent.

For a single-sheet approximation, inspect whether the running Blender version supports the intended thin-surface model. Do not invent a socket or treat thin-film interference as a thin-wall setting. If correct appearance needs added thickness, explain that geometry dependency.

For clear windows, keep the optical glazing separate from the outside photograph. Follow [window views](../../build-interior-scene/references/window-views.md) for the exterior card and visibility through transmission; an opaque photo assigned to the pane removes the glass behavior.

When food or decor looks too small or obscured inside a container, separate its geometry from the optical effect. In an authorized diagnostic pass, temporarily hide only the target glass and render the same camera to inspect the contents directly. Record and restore the original visibility before saving an accepted scene or rendering the final, including cleanup after a failed diagnostic. Follow the [render lifecycle](../../light-and-render-interior/references/render-lifecycle.md) and restore only when Blender is idle; an MCP timeout alone does not establish that the render ended. Undersized contents can require a geometry correction rather than a shader change. This diagnostic removes optical effects and is not a final comparison of the glass material. Recheck the restored container and use [reflection diagnosis](../../light-and-render-interior/references/photographic-lighting.md#trace-reflections-before-changing-materials) when a light source is concealing the contents.

## Leaves and petals

Preserve atlas color, vertex-color variation, normals, and cutout masks. Apply translucency to the foliage region, keeping stems and pots on their appropriate surfaces.

Keep cutout transparency around the whole opaque/translucent leaf combination. Apply the alpha mask once; feeding it into the leaf shader and masking the same result again can weaken edges. Inspect front and back lighting, shadow silhouettes, and the space between leaves for visible rectangular cards.

Material work can improve waxiness, flatness, and light transmission. Repeated silhouettes or crude flower shapes require geometry or asset changes within the broader task.

## Metal, ceramic, and coated appliances

Distinguish bare metal from paint, ceramic, or plastic. Use metallic response for exposed metal and dielectric response for those nonmetal surfaces; preserve masks separating them on imported assets. Match roughness and any actual coating to the finish.

Check the reflected surroundings before changing a metal's base color to compensate for a dark render. Add fingerprints, scratches, or edge wear only when supported by the brief or reference, at a scale that survives the intended framing.

For distracting dots, bright bands, or mirror-like appliance highlights, use [controlled reflection diagnosis](../../light-and-render-interior/references/photographic-lighting.md#trace-reflections-before-changing-materials) before flattening the finish. Preserve imported masks for plastic grips, painted regions, and exposed metal while tuning a replacement asset. Missing dish thickness or an incorrect appliance opening belongs to [kitchen construction](../../build-interior-scene/references/kitchen-construction.md), not the ceramic or metallic response.

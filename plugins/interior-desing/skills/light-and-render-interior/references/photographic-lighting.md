# Photographic lighting

Use for lighting and exposure work. For a render-only task, preserve the established setup and inspect it only as needed to produce the requested output.

## Principal light and ambient fill

Identify the apparent light direction in the reference: window/sky, sun, large interior source, or practical fixtures. Use geometry and source placement that explain the observed shadows and highlights. Establish a readable principal light before adding fill.

Broad light sources soften shadows and shape large reflections. Excessive frontal fill or cove intensity can remove the contrast that gives cabinets and chairs depth. Check a few important surfaces in the image instead of judging only the average room brightness.

For exterior contribution, inspect windows, glazing, wall thickness, and unintended blockers. An environment texture is optional; use it when its light and reflection content suit the scene. Keep downloaded HDRIs local with provenance and a portable scene path. A world color or appropriate area light can also support the task without acquiring a new asset.

When the window is in frame, provide an intentional visible exterior as well as daylight. Follow [window views](../../build-interior-scene/references/window-views.md) for a photographic backdrop plane. Match the photograph's light direction and weather to the room lighting, and check that the card neither blocks daylight nor adds unwanted illumination. Keep an approved camera and light rig stable while verifying the view.

## Practical fixtures and mixed light

Model the emitting region and its supporting light consistently. A bright visible strip and an extra light can double the intended contribution. Use an additional sampling-friendly source deliberately and check that its reflections and spill do not contradict the fixture.

For a lamp that should illuminate its shade, inspect the light's position relative to the bulb mesh, shade, socket, and support geometry. A point light enclosed by an opaque decorative bulb can be blocked by its own proxy. Correct the bulb material or source representation; when a separate light represents the visible bulb's output, a documented shadow-visibility exception for that proxy can be appropriate. Preserve occlusion from the shade, socket, and supports. Verify shade glow and spill together with exposure fixed, and account for both mesh emission and any added light. Follow [lampshade fabric](../../cycles-materials/references/surfaces.md#lampshade-fabric) for shell and scattering checks; an intentionally unlit lamp needs no glow.

Balance warm practicals against the ambient contribution using the reference and neutral surfaces. Avoid tinting every material orange to simulate warm illumination. Preserve subtle cool/warm relationships where they exist; a neutral room brief does not inherit the warm palette of a previous kitchen.

## Exposure and color

Set the view transform, look, exposure, and white balance as a coordinated photographic choice. AgX is a suitable starting point for many interiors when no transform is specified; retain an existing approved transform for comparisons. Its highlight handling does not repair weak geometry, unsuitable textures, or flat lighting. [Blender display and view transforms](https://docs.blender.org/manual/sl/5.2/render/color_management/displays_views.html)

Inspect window highlights, light fittings, dark furniture, and neutral walls together. Clipped highlights, crushed interiors, or a pervasive color cast may need a source-balance change rather than only an exposure offset. Avoid applying the display transform twice when comparing a display-ready PNG to linear render data.

## Camera and detail

Use the established camera height, lens, framing, and vertical treatment. If camera work is requested, save a separate composition pass so lighting/material comparisons remain interpretable. Set focus on an intentional subject and judge depth of field at final output size; excessive blur can make an architectural view feel miniature.

Check contact shadows, glass reflections, ceiling bounce, and foreground leaves in the complete image. Inspect detail crops for noise and denoising smears before choosing final sampling. A technically clean crop does not prove that the whole room's illumination works.

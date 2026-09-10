# Views through windows

Treat the outside view as part of the composition whenever a clear window is visible. For a fixed camera and distant scenery, use a suitable real exterior photograph on a plane beyond the window. Preserve an explicitly requested frosted, obscured, or deliberately blown-out treatment.

## Choose the view

Use a supplied image or find a suitable photograph through image/web search. Match the room's intended setting, apparent floor height, horizon, perspective, season, weather, and daylight direction. An eye-level garden photo and an upper-floor city view imply different surroundings. Favor enough quiet detail to establish an exterior without distracting from the room.

Download a usable-resolution original from a source that permits the intended reuse. Save its source page, author/license information, and required credit with the local image. Inspect the actual image rather than relying on a search thumbnail. Pack it into the `.blend` or retain a portable relative path.

## Place the photograph beyond the glazing

Create a separate named mesh plane outside the room through Blender MCP and map the photograph to it. Keep the glazing, frame, and sill as their own geometry; the photograph belongs behind them rather than on the glass material.

Use the saved camera to position and size the plane. Preserve the image's aspect ratio, align the horizon and visible verticals, and cover all visible panes with margin for refraction, framing adjustments, and relevant reflections. Keep plane edges, repeated texture borders, and nearby exterior blockers out of the opening. For one continuous window, use a coherent view across its panes.

A distant plane approximates a distant view. Near balconies, nearby buildings, large camera moves, or views facing different directions may need exterior geometry, several coordinated views, or an appropriate environment instead. Check each delivered camera; a single photograph does not supply general 3D parallax.

## Make the image readable without changing the daylight accidentally

Use an image-driven unlit/emission appearance when ordinary diffuse shading makes the photograph look like a dark board. Adjust brightness against the final room exposure; avoid turning the photo into an overbright luminous rectangle. A textured mesh plane can be built directly without installing an image-import add-on. [Blender image-plane material options](https://docs.blender.org/manual/en/3.6/addons/import_export/images_as_planes.html)

Keep the established sun, sky/environment, or area lights responsible for the intended illumination. Inspect the card's shadow and indirect-light contribution. For a backdrop that should not block daylight, disable its shadow visibility and control unwanted diffuse/volume contribution with the available Cycles ray settings or a suitable light-path shader. Verify the result rather than assuming an emissive image has no lighting effect.

Keep it visible through the actual glass: Camera visibility alone is insufficient after a refractive surface; preserve Transmission visibility and the Glossy/reflection visibility needed by the shot. Check parent/instance visibility too. [Cycles ray visibility](https://docs.blender.org/manual/nl/5.2/render/cycles/object_settings/object_data.html)

## Verify through the finished window

Render a crop with the actual glazing and final color management, then inspect the full composition. Confirm a believable view, continuous framing across panes, sensible exterior brightness, retained glass reflections, and no card edges or unintended shadows. Compare room illumination before and after the card so the view does not silently replace the lighting design.

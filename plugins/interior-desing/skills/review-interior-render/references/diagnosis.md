# Diagnose the visible cause

Use these as hypotheses to test, not a list of automatic edits. Inspect actual render pixels at a useful scale before selecting a row.

| Visible symptom | Inspect first | Correction when confirmed |
| --- | --- | --- |
| Room feels wrong despite detailed props | Camera height/lens, major dimensions, overlaps and negative spaces | Correct composition or the dominant geometry before adding detail. |
| Chair or flower still looks fabricated | Silhouette, repeated forms, cushion thickness, petal/leaf construction, shading normals | Improve the geometry or use a suitable asset when in scope; surface noise cannot change silhouette. |
| Rug reads as a rigid panel or has floating furniture | Pile/backing thickness, edge profile, separate border strips, floor and foot contacts | Correct the [textile geometry and support](../../build-interior-scene/SKILL.md) before increasing bump; judge weave at delivery resolution. |
| A lit fabric shade stays opaque or glows uniformly | Shell layers/Solidify, scattering material, bulb proxy occlusion, source placement, texture scale | Check [shade construction and fabric](../../cycles-materials/references/surfaces.md#lampshade-fabric) and the actual light path; verify glow and spill without hiding all fixture shadows. |
| Dark grooves outline continuous wall–ceiling junctions | Evaluated bevels at internal contact edges, gaps, normals, and intended reveals | Close unintended seams and restrict bevels to appropriate exposed edges; preserve designed shadow gaps and check for light leaks. |
| Leather reads as plastic | Connected roughness data, coat contribution, normal scale, source atlas, reflected light shape | Correct map interpretation, preserve folds, and tune the intended surface finish. |
| Straight line or grid crosses a slab | Source color/roughness/normal maps, actual UV input and render-active layer | Select coherent mapping and a continuous source region or slab texture; avoid blindly raising samples. |
| Wood grain or pores are enormous | Object dimensions, scene units, mapping coordinates, source aspect ratio | Calibrate physical texture coverage and grain direction. |
| Glass is dark, cloudy, or disappears | Thickness, normals, overlapping surfaces, transmission/IOR, absorption scale, reflection surroundings | Correct the demonstrated optical/geometry issue; random alpha reduction is not a general solution. |
| A clear window looks like a blank panel or exposes a backdrop edge | Missing exterior content, source photograph/perspective, card bounds, glazing and ray visibility | Add or correct a coherent [outside view](../../build-interior-scene/references/window-views.md), then verify visibility through glass and unchanged intended daylight. |
| Leaf cards show rectangles or faint doubled edges | Alpha source and how often it is applied; mask coverage across shader branches | Preserve the cutout around the complete leaf shader and inspect front/back lighting. |
| Room is evenly bright and flat | Principal-light direction, fill/cove intensity, source size, room enclosure | Rebalance the lights when lighting is in scope; more fill may worsen depth. |
| Details look waxy or smeared | Raw versus denoised output when available, sampling/time cap, output resolution | Improve the sampling/denoising tradeoff after ruling out missing surface detail. |
| New pass is brighter or softer | Exposure/view transform, crop, focus, resolution, denoiser, then scene changes | Establish common comparison conditions before claiming a material improvement. |

When several causes are plausible, use the smallest test that separates them. For example, inspect the source image and UV path before rebuilding a countertop, or compare a crop with consistent exposure before reworking an entire light rig.

Prioritize visible and requested problems. Avoid adding scratches, grime, strong depth of field, or a different renderer as generic realism treatments. A clean modern interior can be realistic; imperfections need to suit the object and brief.

Keep technical and visual evidence distinct. A file hash can identify a pass, a graph audit can confirm the connected nodes, and render logs can confirm device use. Only inspecting the rendered image can support a claim about its visible appearance.

---
name: find-3d-models
description: Use when a user wants to find, compare, or download an existing 3D model of a requested object, furniture item, plant, appliance, or prop for Blender, Three.js, or another 3D scene, including matching an object in a reference image.
---

# Find 3D Models

Find an existing, downloadable model that fits the requested object and its intended use. Default to free assets and realistic materials; preserve the user's explicit style, budget, provider, and format choices.

## Understand the object

Extract the object category, silhouette, material, color, style, scale, and intended renderer from the request or reference image. Use the current task's constraints; ask only about missing information that would change selection. Search short object nouns and synonyms separately (for example, “bar stool”, “counter stool”, “stool”). Treat color as adjustable when a material change can satisfy the request; keep distinctive geometry as a stronger constraint.

## Search and select

Read [provider access](references/providers.md) for endpoint syntax, credentials, and file handling.

### Delegate one source per subagent

Use one subagent per source: Poly Haven, ambientCG, BlenderKit, and Sketchfab by default, or only the sources the user requests. Run source searches concurrently within the runtime's agent limit; queue remaining sources as slots become available.

Give each subagent the same object brief, reference image when available, target renderer/format, budget and license constraints, plus its assigned source and the path to the provider reference. Pass secret variable names, never literal credentials. Each subagent searches only its assigned source, checks leading candidates, and returns a small shortlist with the fields and verification levels in “Return a useful match.” It also reports unavailable access or zero matches. Source agents do not create further subagents.

The main agent prepares the comparison criteria while searches run, then collects, deduplicates, and ranks the combined results. It owns the final recommendation and assigns any requested download of a selected asset to a single owner to avoid duplicate work.

If subagents are unavailable or prohibited in the current conversation, the main agent performs the same source searches directly and states that delegation was unavailable. A concurrency limit alone is a reason to queue sources, not skip them.

### Assess candidates

- Search each assigned catalog for suitable matches: Poly Haven and ambientCG for CC0 assets; BlenderKit and Sketchfab for broader object coverage. Don't imply an unqueried catalog was searched.
- Use an available HTTP client, connected provider tool, or browser request API. Load credentials from the runtime environment or secret store. A missing credential skips that provider's authenticated operations while public searches continue. Keep errors distinct from zero matches.
- Begin with object keywords; broaden synonyms if needed. Filter models rather than materials, HDRIs, or whole scenes. Follow pagination only when it can improve an insufficient shortlist. Inspect returned schema and current documentation if an API differs from this reference.
- Rank by geometry and visual fit, verified usage rights, download entitlement, materials/textures, then import effort and file size. For a realistic request, inspect previews of leading candidates when tools permit; label a metadata-only assessment when previews cannot be viewed. High polygon counts alone do not establish realism.
- Prefer CC0 when the raw model will be served to browsers or redistributed. Check other licenses against that use. A free price, valid API key, and asset reuse license are separate facts.
- For Three.js, prefer a self-contained GLB when available. Verify the chosen asset's actual formats; catalog-wide format claims are insufficient. Preserve Blender-native assets when the requested workflow needs them.

## Return a useful match

Recommend one model and, when helpful, a few alternatives. Include each asset's stable source link, provider/ID, author, license, why it fits, available formats, known size/texture resolution, required conversion, and verification level. Mark unavailable facts as unknown; keep raw API dumps out of the reply.

Use these verification levels accurately: **listed** (search/detail returned), **download available** (current entitlement or file metadata checked), **download verified** (bytes and contents checked), **import verified** (opened in the target tool). Briefly report providers that were unavailable. Preserve asset IDs and source URLs; signed download URLs expire and are not permanent references.

## When download is requested

Fetch the selected resolution into the user's requested asset directory or an isolated task directory. Inspect file signatures, sizes and provided checksums; check glTF/OBJ dependencies or archive contents. Account for MTL options such as `-bm 1` when resolving texture paths. Extract only paths within the destination directory. Save provenance with the asset: source URL, provider/ID, author, license/link, selected format/resolution, and verification performed.

Use the API token only on its provider's authenticated API. Fetch signed CDN URLs without that token. Keep secrets out of skill files, URLs, output, and logs. Place credentials in sandbox secrets rather than in the copied skill. Uploading to S3, changing a scene, purchasing assets, and configuring a public multiuser download service require their own task scope.

---
name: review-interior-render
description: Use when judging an interior render against a reference or earlier pass, diagnosing a synthetic appearance or visual regression, or selecting targeted realism improvements. Applies to rendered-image evidence and the edit-review loop, not just render status checks.
---

# Review an interior render

Inspect the image that was actually produced, identify the dominant visual problems, and connect each proposed correction to evidence. Shader complexity, polygon counts, and a successful render status are not measures of visual improvement.

## Establish a fair comparison

Open the latest completed image, the reference or brief, and the previous accepted pass when available. Inspect both the full composition and relevant detail crops. Read the corresponding scene/render record so the image is tied to a known camera and revision.

Check framing, resolution/crop, exposure, view transform, and denoising differences before drawing a before/after conclusion. If they differ, describe the confounders. For an authorized improvement task, establish a comparison under the chosen common settings before attributing a change to materials. Do not silently reinterpret a linear image as a display-ready PNG.

When images cannot be opened, report the review as limited to scene/settings evidence. Do not infer that a render looks realistic from node inspection alone.

## Diagnose before editing

Read [diagnosis guide](references/diagnosis.md) for symptom-driven checks. Separate observations from hypotheses. Confirm likely causes through targeted Blender MCP inspection, source-image inspection, or a small controlled render.

Rank the few defects that most affect the user's goal by their screen area, visual prominence, and mismatch to the reference. A dominant wrong silhouette can matter more than a small texture flaw. Within a material-only request, report geometry or lighting limits while keeping edits in scope.

Return each finding in this compact form:

| Region/object | Visible evidence | Likely cause and confirming check | Proposed correction | Comparison to verify it |
| --- | --- | --- | --- | --- |
| Targeted surface or feature | What can actually be seen | What is known versus still uncertain | A bounded edit tied to the cause | Image/crop and settings to keep fixed |

Use as many rows as materially useful; avoid a generic checklist of defects not present in the image. Where a numeric setting is uncertain, present it as a starting hypothesis rather than a universal realism value.

## Act according to the request

For a review-only request, deliver the findings and their priority without modifying the scene.

For an instruction to fix or improve, preserve the previous scene and image, then perform the authorized corrections. Use [cycles-materials](../cycles-materials/SKILL.md), [build-interior-scene](../build-interior-scene/SKILL.md), or [light-and-render-interior](../light-and-render-interior/SKILL.md) for the relevant cause. Continue through a completed comparison render; do not stop at a critique when the user requested an improved result.

Change a small coherent set of variables per pass. Compare the original defect and nearby regions for regressions, then retain the better result or restore the earlier checkpoint. Keep rejected passes identifiable rather than overwriting them. Stop iterating when the requested defects are addressed or remaining limits require unavailable inputs, scope changes, or more resources than the user allowed.

Deliver the inspected image(s), corresponding native scene for edited work, what visibly improved or regressed, and remaining limits. Distinguish a faithful approximation from an exact reconstruction and technical completion from visual success.

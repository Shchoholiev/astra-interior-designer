import { Matrix4, PerspectiveCamera, Quaternion, Vector3, type Object3D } from "three";

export type RenderViewContext = ReturnType<typeof captureRenderView>;
export const RENDER_VIEW_CONTEXT_MARKER = "Viewer camera context for this render:";

// Hash the already-loaded glTF document and buffers, not a second fetch of an
// S3 key that may have been overwritten since the viewer loaded it.
export async function fingerprintScene(document: unknown, buffers: ArrayBuffer[]) {
  const parts = [new TextEncoder().encode(JSON.stringify(document)), ...buffers.map((buffer) => new Uint8Array(buffer))];
  const bytes = new Uint8Array(parts.reduce((length, part) => length + 4 + part.byteLength, 0));
  const view = new DataView(bytes.buffer);
  let offset = 0;
  for (const part of parts) {
    view.setUint32(offset, part.byteLength, true);
    bytes.set(part, offset + 4);
    offset += 4 + part.byteLength;
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return `gltf-content-sha256:${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export function captureRenderView(camera: PerspectiveCamera, scene: Object3D, sceneUrl: string, fingerprint: string) {
  camera.updateWorldMatrix(true, false);
  scene.updateWorldMatrix(true, false);
  const width = camera.aspect >= 1 ? 4096 : Math.max(1, Math.round(4096 * camera.aspect));
  const height = camera.aspect >= 1 ? Math.max(1, Math.round(4096 / camera.aspect)) : 4096;
  const asset = new URL(sceneUrl);
  // Never send signed URL credentials to the chat/agent.
  asset.search = "";
  asset.hash = "";
  return {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    scene: { asset: asset.toString(), fingerprint, immutableVersion: null },
    camera: {
      type: "perspective",
      coordinateSpace: "Three.js viewer world, right-handed Y-up; camera local -Z forward, +Y up",
      position: camera.getWorldPosition(new Vector3()).toArray(),
      quaternionXYZW: camera.getWorldQuaternion(new Quaternion()).toArray(),
      verticalFovDegrees: camera.getEffectiveFOV(),
      aspect: camera.aspect,
      near: camera.near,
      far: camera.far,
      projectionMatrixColumnMajor: camera.projectionMatrix.toArray(),
    },
    transforms: {
      viewerWorldFromGltfColumnMajor: scene.matrixWorld.toArray(),
      // Standard Blender glTF exporter: (x, y, z) -> (x, z, -y).
      gltfFromBlenderColumnMajor: new Matrix4().makeRotationX(-Math.PI / 2).toArray(),
    },
    output: { format: "png", width, height, preserveFraming: true },
  };
}

export function renderViewMessage(context: RenderViewContext) {
  return [
    "Create a photorealistic Blender render of this view. Refine the materials, surface details, and lighting while preserving the room layout, furniture placement, selected camera, and aspect ratio. Return the high-resolution image in this chat.",
    RENDER_VIEW_CONTEXT_MARKER,
    JSON.stringify(context, null, 2),
    "Quaternion order is x,y,z,w. Matrices are column-major. Undo viewerWorldFromGltf, then undo gltfFromBlender to map the world camera pose back into the original Blender scene. Apply the same basis conversion to the camera rotation, not just its position. Both cameras look along local -Z with local +Y up. Use the effective vertical FOV and the supplied aspect; output dimensions are rounded to whole pixels. If importing the GLB into a new Blender scene, account for the importer's axis conversion instead of applying it twice.",
    "The fingerprint identifies the glTF document and buffers loaded by the viewer, not the signed URL or an immutable S3 version. Verify the source before refinement. Do not silently render a newer/different scene if the source has changed; ask for the view to be refreshed. Keep scene.glb and scene.blend unchanged; save a separate native render copy with its dependencies and save the rendered PNG separately.",
    "Verify the fingerprint against the existing local /workspace/scene.glb; scene.asset is an identifier with private signing credentials deliberately removed, not a public download link. The gltf-content-sha256 algorithm is SHA-256 of these concatenated parts in order: UTF-8 JavaScript JSON.stringify of the parsed glTF JSON document, then each loaded buffer in index order. Prefix EVERY part with its byte length as an unsigned 4-byte LITTLE-ENDIAN integer. For a self-contained GLB, use the parsed JSON chunk and the complete BIN chunk payload, including its padding. Use Node.js JSON.stringify rather than Python JSON serialization, which can format numbers differently. After that content fingerprint matches, compute the same local GLB's whole-file SHA-256 and pass sha256:<that digest> as scene_version to the export helper. This explicitly resolves the helper's different hash scheme; do not substitute the file hash without first verifying the content fingerprint. Map the supplied JSON camera fields into the helper's context fields without changing their values.",
    "This request explicitly authorizes a photorealistic refinement pass in that render copy. The layout preview may intentionally contain simple geometry and flat colors; do not freeze those placeholder surfaces under the export skill's default preserve-materials/lighting rule. Keep room dimensions, openings, furniture footprints, placement, design colors, and exact camera projection fixed. Refine visible object details, bevels, smooth normals, physically scaled materials, and photographic lighting. Use suitable detailed assets where primitive geometry cannot produce the intended silhouette, without rearranging the room.",
    "Read and apply the installed Interior Design SKILL.md files for interior-design, build-interior-scene, cycles-materials, light-and-render-interior, review-interior-render, and export-viewer-render, plus their relevant references. Reading export helper scripts alone does not perform these stages. Inspect the current scene and previous image; correct dominant realism defects such as flat wood without plausible grain, plastic-looking fabric, faceted curved surfaces, and empty or implausibly lit windows when present. Preserve useful existing work rather than replacing every surface indiscriminately.",
    "For a finished residential design, this refinement also permits additive styling in the render copy: apply the plugin’s lived-in interior styling guidance to choose coherent daily-use objects and decor appropriate to the brief. Keep major furniture, openings, clear work areas, and circulation fixed. Respect explicit bare-surface, empty-room, and minimalist styling constraints. Review the complete composition, not just material close-ups.",
    "Review geometry as critically as materials. Texture alone does not make placeholder objects realistic: visible plants need believable curved leaves and branching, fixtures need plausible construction and contact details, and upholstered furniture needs credible volume and seams. Refine or replace such visible placeholders within their established footprints. Inspect window glazing, exterior scale, material grain scale, and reflections for photographic plausibility. Do not accept a visibly simplified object just to preserve its original primitive silhouette; preserve the design intent and placement.",
    "Use native Cycles and the runtime's asynchronous render workflow. Render a modest preview with the exact selected projection, open and inspect the full image and relevant detail crops, and use review-interior-render to correct prominent fixable defects before rendering the final requested dimensions. A successful job or high resolution is not visual acceptance. Use the existing image-delivery workflow only after inspecting the final image; report any remaining visible limitation honestly.",
  ].join("\n\n");
}

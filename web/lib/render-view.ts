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
    "Render a high-resolution PNG of this exact view using Blender. Preserve the room, furniture, materials, camera framing, and aspect ratio. Do not regenerate or modify the scene layout.",
    "Use the existing image-delivery workflow to return the rendered image in this chat.",
    RENDER_VIEW_CONTEXT_MARKER,
    JSON.stringify(context, null, 2),
    "Quaternion order is x,y,z,w. Matrices are column-major. Undo viewerWorldFromGltf, then undo gltfFromBlender to map the world camera pose back into the original Blender scene. Apply the same basis conversion to the camera rotation, not just its position. Both cameras look along local -Z with local +Y up. Use the effective vertical FOV and the supplied aspect; output dimensions are rounded to whole pixels. If importing the GLB into a new Blender scene, account for the importer's axis conversion instead of applying it twice.",
    "The fingerprint identifies the glTF document and buffers loaded by the viewer, not the signed URL or an immutable S3 version. Do not silently render a newer/different scene if the source has changed; ask for the view to be refreshed. Keep scene.glb and scene.blend unchanged; save the rendered PNG separately.",
  ].join("\n\n");
}

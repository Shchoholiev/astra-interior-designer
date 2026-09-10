import assert from "node:assert/strict";
import test from "node:test";
import { Group, Matrix4, PerspectiveCamera, Quaternion, Vector3 } from "three";
import { captureRenderView, fingerprintScene, renderViewMessage } from "../lib/render-view.ts";

const asset = "https://example.s3.amazonaws.com/sandboxes/session/scene.glb?X-Amz-Signature=secret#fragment";

test("captures live world pose, effective FOV, aspect and viewer transform", () => {
  const parent = new Group();
  parent.position.set(10, 2, -4);
  parent.rotation.y = 0.7;
  const camera = new PerspectiveCamera(60, 2, 0.05, 500);
  parent.add(camera);
  camera.position.set(1, 1.65, 3);
  camera.lookAt(0, 0, 0);
  camera.zoom = 2;
  camera.updateProjectionMatrix();
  const scene = new Group();
  scene.position.set(3, 0, 4);
  scene.scale.setScalar(2);
  const context = captureRenderView(camera, scene, asset, "test-fingerprint");
  assert.deepEqual(context.camera.position, camera.getWorldPosition(new Vector3()).toArray());
  assert.deepEqual(context.camera.quaternionXYZW, camera.getWorldQuaternion(new Quaternion()).toArray());
  assert.equal(context.camera.verticalFovDegrees, camera.getEffectiveFOV());
  assert.ok(context.camera.verticalFovDegrees < 60);
  assert.deepEqual(context.transforms.viewerWorldFromGltfColumnMajor, scene.matrixWorld.toArray());
  assert.deepEqual(context.output, { format: "png", width: 4096, height: 2048, preserveFraming: true });
  const capturedPosition = [...context.camera.position];
  camera.position.x += 10;
  assert.deepEqual(context.camera.position, capturedPosition, "snapshot does not follow later movement");
  assert.notDeepEqual(captureRenderView(camera, scene, asset, "test").camera.position, capturedPosition);
});

test("portrait canvas preserves aspect and does not leak signed URL parameters", () => {
  const context = captureRenderView(new PerspectiveCamera(80, 0.5), new Group(), asset, "test");
  assert.equal(context.output.width, 2048);
  assert.equal(context.output.height, 4096);
  const text = renderViewMessage(context);
  assert.ok(text.includes("Viewer camera context"));
  assert.ok(text.includes("existing image-delivery workflow"));
  assert.ok(text.includes("scene.glb and scene.blend unchanged"));
  assert.ok(!text.includes("secret"));
  assert.ok(!text.includes("X-Amz"));
  assert.equal(context.scene.immutableVersion, null);
});

test("Blender basis and viewer transform can be inverted for a world camera pose", () => {
  const camera = new PerspectiveCamera();
  const scene = new Group();
  scene.position.set(8, 2, 4);
  scene.rotation.y = 0.3;
  scene.scale.setScalar(2);
  const context = captureRenderView(camera, scene, asset, "test");
  const basis = new Matrix4().fromArray(context.transforms.gltfFromBlenderColumnMajor);
  assert.ok(new Vector3(1, 2, 3).applyMatrix4(basis).distanceTo(new Vector3(1, 3, -2)) < 1e-10);
  const viewer = new Matrix4().fromArray(context.transforms.viewerWorldFromGltfColumnMajor);
  const original = new Matrix4().compose(new Vector3(1, 2, 3), new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), 0.5), new Vector3(1, 1, 1));
  const world = viewer.clone().multiply(basis).multiply(original);
  const restored = basis.clone().invert().multiply(viewer.clone().invert()).multiply(world);
  restored.elements.forEach((value, index) => assert.ok(Math.abs(value - original.elements[index]) < 1e-10));
});

test("fingerprint is stable and changes with either model metadata or geometry", async () => {
  const bytes = new Uint8Array([1, 2, 3]).buffer;
  const first = await fingerprintScene({ asset: { version: "2.0" } }, [bytes]);
  assert.match(first, /^gltf-content-sha256:[0-9a-f]{64}$/);
  assert.equal(first, await fingerprintScene({ asset: { version: "2.0" } }, [bytes]));
  assert.notEqual(first, await fingerprintScene({ asset: { version: "2.0" } }, [new Uint8Array([1, 2, 4]).buffer]));
  assert.notEqual(first, await fingerprintScene({ asset: { version: "2.0" }, extras: { revision: 2 } }, [bytes]));
});

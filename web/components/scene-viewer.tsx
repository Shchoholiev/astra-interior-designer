"use client";

import { Bounds, OrbitControls, PointerLockControls, useBounds, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Box, Camera, Footprints, LoaderCircle, Rotate3D } from "lucide-react";
import { Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Box3, MathUtils, PerspectiveCamera, Raycaster, Vector3 } from "three";

import { Button } from "@/components/ui/button";
import { captureRenderView, fingerprintScene, type RenderViewContext } from "@/lib/render-view";

type SceneViewerProps = {
  sceneUrl: string | null;
  progress: { label: string } | null;
  title?: string | null;
  onRenderView?: (context: RenderViewContext) => void;
};

type ViewCapture = { sceneUrl: string; capture: () => RenderViewContext };

function Room({ sceneUrl, mode, fitVersion, onCaptureReady }: { sceneUrl: string; mode: "orbit" | "walk"; fitVersion: number; onCaptureReady: (capture: ViewCapture | null) => void }) {
  const { scene, parser } = useGLTF(sceneUrl, "/draco/");
  const { camera } = useThree();
  const bounds = useMemo(() => new Box3().setFromObject(scene), [scene]);
  const radius = Math.max(bounds.getSize(new Vector3()).length() / 2, 0.1);
  useEffect(() => {
    scene.traverse((object) => {
      if ("castShadow" in object) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
  }, [scene]);
  useEffect(() => {
    let active = true;
    onCaptureReady(null);
    const prepare = async () => {
      const buffers: ArrayBuffer[] = await parser.getDependencies("buffer");
      const fingerprint = await fingerprintScene(parser.json, buffers);
      if (active && camera instanceof PerspectiveCamera) {
        onCaptureReady({ sceneUrl, capture: () => captureRenderView(camera, scene, sceneUrl, fingerprint) });
      }
    };
    prepare().catch(() => { if (active) onCaptureReady(null); });
    return () => { active = false; };
  }, [camera, scene, parser, sceneUrl, onCaptureReady]);
  return (
    <>
      <primitive object={scene} />
      {mode === "orbit" && <>
        <OrbitControls makeDefault minDistance={radius * 0.05} maxDistance={radius * 12} maxPolarAngle={Math.PI / 2.04} />
        <Bounds margin={1.35} maxDuration={0}>
          <FitScene bounds={bounds} fitVersion={fitVersion} />
        </Bounds>
      </>}
      {mode === "walk" && <WalkController sceneUrl={sceneUrl} bounds={bounds} />}
    </>
  );
}

function FitScene({ bounds, fitVersion }: { bounds: Box3; fitVersion: number }) {
  const api = useBounds();
  const { size, controls } = useThree();
  useEffect(() => {
    // makeDefault changes after mount; don't fit against the old walk controls.
    if (!controls || !("target" in controls)) return;
    api.refresh(bounds);
    const { center, distance } = api.getSize();
    const position = center.clone().addScaledVector(new Vector3(1, 1.25, 1).normalize(), distance);
    api.moveTo(position).lookAt({ target: center }).clip();
  }, [api, bounds, fitVersion, size.width, size.height, controls]);
  return null;
}

function CameraLens({ mode }: { mode: "orbit" | "walk" }) {
  const { camera, size } = useThree();
  const cameraRef = useRef(camera);
  useLayoutEffect(() => {
    cameraRef.current = camera;
    const lens = cameraRef.current;
    if (lens instanceof PerspectiveCamera) {
      // Keep a useful horizontal view even when the chat leaves a narrow canvas.
      const walkFov = MathUtils.radToDeg(2 * Math.atan(Math.tan(MathUtils.degToRad(80 / 2)) / Math.min(size.width / size.height, 1)));
      lens.fov = mode === "walk" ? Math.min(walkFov, 110) : 50;
      lens.zoom = 1;
      lens.updateProjectionMatrix();
    }
  }, [camera, mode, size.width, size.height]);
  return null;
}

function WalkController({ sceneUrl, bounds }: { sceneUrl: string; bounds: Box3 }) {
  const { scene } = useGLTF(sceneUrl, "/draco/");
  const { camera } = useThree();
  const cameraRef = useRef(camera);
  const controls = useRef<React.ComponentRef<typeof PointerLockControls>>(null);
  const keys = useRef(new Set<string>());
  const forward = useRef(new Vector3());
  const right = useRef(new Vector3());
  const scale = Math.max(bounds.max.y - bounds.min.y, 0.1) / 2.8;

  useEffect(() => {
    cameraRef.current = camera;
    const activeCamera = cameraRef.current;
    const size = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    const ray = new Raycaster();
    let bestScore = -Infinity;
    let start = new Vector3(center.x, bounds.min.y + 1.65 * scale, center.z);
    let heading = new Vector3(0, 0, -1);
    // Sample floor positions and choose clearance from walls/furniture, rather
    // than spawning at the old classroom coordinates or inside the center wall.
    for (let x = 1; x < 10; x++) for (let z = 1; z < 10; z++) {
      const point = new Vector3(bounds.min.x + size.x * x / 10, bounds.min.y + 1.65 * scale, bounds.min.z + size.z * z / 10);
      ray.set(point, new Vector3(0, -1, 0));
      const floor = ray.intersectObject(scene, true)[0];
      if (!floor || floor.point.y > bounds.min.y + 0.4 * scale) continue;
      point.y = floor.point.y + 1.65 * scale;
      let clearance = Infinity;
      let longest = -1;
      let direction = heading;
      for (let i = 0; i < 8; i++) {
        const look = new Vector3(Math.sin(i * Math.PI / 4), 0, Math.cos(i * Math.PI / 4));
        ray.set(point, look);
        const distance = ray.intersectObject(scene, true)[0]?.distance ?? size.length();
        clearance = Math.min(clearance, distance);
        if (distance > longest) { longest = distance; direction = look; }
      }
      if (clearance > bestScore) { bestScore = clearance; start = point; heading = direction; }
    }
    activeCamera.position.copy(start);
    activeCamera.lookAt(start.clone().add(heading).add(new Vector3(0, -0.3, 0)));
    activeCamera.near = Math.max(0.005, scale * 0.01);
    activeCamera.far = Math.max(size.length() * 20, 100 * scale);
    if (activeCamera instanceof PerspectiveCamera) activeCamera.updateProjectionMatrix();
    const down = (event: KeyboardEvent) => {
      if (!controls.current?.isLocked) return;
      keys.current.add(event.code);
      if (event.code.startsWith("Arrow")) event.preventDefault();
    };
    const up = (event: KeyboardEvent) => keys.current.delete(event.code);
    const clear = () => keys.current.clear();
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", clear);
      clear();
    };
  }, [camera, bounds, scene, scale]);

  useFrame((_, delta) => {
    if (!controls.current?.isLocked) return;
    const activeCamera = cameraRef.current;
    activeCamera.getWorldDirection(forward.current);
    forward.current.y = 0;
    forward.current.normalize();
    right.current.crossVectors(forward.current, activeCamera.up).normalize();
    const speed = Math.min(delta, 0.05) * 2.3 * scale;
    if (keys.current.has("KeyW") || keys.current.has("ArrowUp")) activeCamera.position.addScaledVector(forward.current, speed);
    if (keys.current.has("KeyS") || keys.current.has("ArrowDown")) activeCamera.position.addScaledVector(forward.current, -speed);
    if (keys.current.has("KeyA") || keys.current.has("ArrowLeft")) activeCamera.position.addScaledVector(right.current, -speed);
    if (keys.current.has("KeyD") || keys.current.has("ArrowRight")) activeCamera.position.addScaledVector(right.current, speed);
    activeCamera.position.x = MathUtils.clamp(activeCamera.position.x, bounds.min.x, bounds.max.x);
    activeCamera.position.z = MathUtils.clamp(activeCamera.position.z, bounds.min.z, bounds.max.z);
  });

  return <PointerLockControls ref={controls} makeDefault selector="[aria-label='Interactive 3D room'] canvas" onUnlock={() => keys.current.clear()} />;
}

export function SceneViewer({ sceneUrl, progress, title, onRenderView }: SceneViewerProps) {
  const [mode, setMode] = useState<"orbit" | "walk">("orbit");
  const [fitVersion, setFitVersion] = useState(0);
  const [viewCapture, setViewCapture] = useState<ViewCapture | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const renderCurrentView = () => {
    if (!onRenderView || progress || viewCapture?.sceneUrl !== sceneUrl) return;
    try {
      setRenderError(null);
      // Read the live camera on click, not its initial pose or last React render.
      onRenderView(viewCapture.capture());
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : "Unable to capture this view.");
    }
  };

  return (
    <section className="relative h-full overflow-hidden bg-[#c7d0cc]" aria-label="Interactive 3D room">
      <Canvas shadows camera={{ position: [8, 10, 8], fov: 50 }}>
        <color attach="background" args={["#c7d0cc"]} />
        <CameraLens mode={mode} />
        <ambientLight intensity={2.2} />
        <hemisphereLight intensity={1.8} color="#fff3dd" groundColor="#68736d" />
        <directionalLight castShadow intensity={3.4} position={[2, 5, 4]} shadow-mapSize={[2048, 2048]} />
        {sceneUrl && <Suspense fallback={null}><Room key={sceneUrl} sceneUrl={sceneUrl} mode={mode} fitVersion={fitVersion} onCaptureReady={setViewCapture} /></Suspense>}
      </Canvas>

      <header className="absolute left-4 right-4 top-4 flex items-center rounded-2xl border border-white/40 bg-[#f7f4ed]/90 px-4 py-3 shadow-xl backdrop-blur-xl">
        <div><p className="text-[11px] font-bold uppercase tracking-[.11em] text-[#6e7770]">Current scene</p><h2 className="font-serif text-lg">{title || "Untitled room"}</h2></div>
        <span className="ml-auto flex items-center gap-2 text-sm"><i className={`size-2 rounded-full ${sceneUrl ? "bg-emerald-700 ring-4 ring-emerald-700/10" : "bg-[#9aa19c]"}`} />{sceneUrl ? "Generated scene" : "No scene yet"}</span>
      </header>

      {sceneUrl && onRenderView && <div className="absolute right-4 top-24 z-10">
        <Button onClick={renderCurrentView} disabled={Boolean(progress) || viewCapture?.sceneUrl !== sceneUrl} className="rounded-full bg-[#193d2e] text-white shadow-lg" title="Ask the agent for a high-resolution Blender PNG from your current camera"><Camera />Render this view</Button>
      </div>}
      {renderError && <p role="alert" className="absolute inset-x-4 top-36 rounded-lg bg-white p-3 text-sm text-red-700">{renderError}</p>}

      {sceneUrl && <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border border-white/20 bg-[#17221c]/85 p-1.5 text-white shadow-xl backdrop-blur-xl">
        <Button onClick={() => setMode("orbit")} size="sm" className={mode === "orbit" ? "rounded-full bg-white text-[#17221c] hover:bg-white/90" : "rounded-full bg-transparent text-white hover:bg-white/10 hover:text-white"}><Rotate3D />Orbit</Button>
        <Button onClick={() => setMode("walk")} size="sm" className={mode === "walk" ? "rounded-full bg-white text-[#17221c] hover:bg-white/90" : "rounded-full bg-transparent text-white hover:bg-white/10 hover:text-white"}><Footprints />Walk</Button>
        <Button onClick={() => { setMode("orbit"); setFitVersion((value) => value + 1); }} size="icon-sm" variant="ghost" className="rounded-full text-white hover:bg-white/10 hover:text-white" aria-label="Fit scene"><Box /></Button>
      </div>}

      {sceneUrl && mode === "walk" && !progress && <div className="pointer-events-none absolute inset-x-0 bottom-20 mx-auto w-fit rounded-full bg-[#17221c]/80 px-4 py-2 text-xs text-white backdrop-blur">Click the room, then use WASD · Esc releases the cursor</div>}

      {progress && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[#17221c]/35 backdrop-blur-[2px]">
          <div className="w-[min(380px,calc(100%-32px))] rounded-2xl border border-white/45 bg-[#fbf8f1]/95 p-5 shadow-2xl">
            <div className="flex items-center gap-3"><LoaderCircle className="size-5 animate-spin text-[#1d513a]" /><strong className="font-serif text-lg">{sceneUrl ? "Updating your room" : "Creating your room"}</strong></div>
            <p className="mt-3 text-sm text-[#657069]">{progress.label}</p>
            <p className="mt-1 text-xs text-[#858c87]">{sceneUrl ? "The current scene stays available until the new version is ready." : "Your interactive scene will appear here when it is ready."}</p>
          </div>
        </div>
      )}
    </section>
  );
}

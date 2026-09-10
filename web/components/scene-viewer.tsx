"use client";

import { Html, OrbitControls, PointerLockControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Box, Footprints, LoaderCircle, Rotate3D } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { MathUtils, Vector3 } from "three";

import { Button } from "@/components/ui/button";

type SceneViewerProps = {
  sceneUrl: string | null;
  progress: { label: string } | null;
};

const presets = {
  overview: { position: [2.58, 1.55, 4.47], target: [1.3, 1.35, -0.4] },
  entry: { position: [3.25, 1.65, 3.85], target: [0, 1.35, 0.25] },
  desks: { position: [-0.2, 1.65, 2.65], target: [-0.7, 1.25, -2.4] },
} as const;

function Room({ sceneUrl }: { sceneUrl: string }) {
  const { scene } = useGLTF(sceneUrl, "/draco/");
  useEffect(() => {
    scene.traverse((object) => {
      if ("castShadow" in object) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
  }, [scene]);
  return <primitive object={scene} />;
}

function ModelLoading() {
  return (
    <Html center>
      <div className="w-44 rounded-2xl bg-[#f7f4ed]/95 p-4 text-center text-sm shadow-xl backdrop-blur">
        <strong className="block font-serif">Loading room</strong>
        <span className="mt-1 block text-xs text-[#657069]">Preparing interactive preview…</span>
      </div>
    </Html>
  );
}

function CameraPosition({ preset }: { preset: keyof typeof presets }) {
  const { camera } = useThree();
  useEffect(() => {
    const [x, y, z] = presets[preset].position;
    const [tx, ty, tz] = presets[preset].target;
    camera.position.set(x, y, z);
    camera.lookAt(tx, ty, tz);
  }, [camera, preset]);
  return null;
}

function WalkController() {
  const { camera } = useThree();
  const cameraRef = useRef(camera);
  const keys = useRef(new Set<string>());
  const forward = useRef(new Vector3());
  const right = useRef(new Vector3());

  useEffect(() => {
    cameraRef.current = camera;
    camera.position.set(3.7, 1.65, 4.15);
    const down = (event: KeyboardEvent) => keys.current.add(event.code);
    const up = (event: KeyboardEvent) => keys.current.delete(event.code);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [camera]);

  useFrame((_, delta) => {
    const activeCamera = cameraRef.current;
    activeCamera.getWorldDirection(forward.current);
    forward.current.y = 0;
    forward.current.normalize();
    right.current.crossVectors(forward.current, activeCamera.up).normalize();
    const speed = Math.min(delta, 0.05) * 2.3;
    if (keys.current.has("KeyW") || keys.current.has("ArrowUp")) activeCamera.position.addScaledVector(forward.current, speed);
    if (keys.current.has("KeyS") || keys.current.has("ArrowDown")) activeCamera.position.addScaledVector(forward.current, -speed);
    if (keys.current.has("KeyA") || keys.current.has("ArrowLeft")) activeCamera.position.addScaledVector(right.current, -speed);
    if (keys.current.has("KeyD") || keys.current.has("ArrowRight")) activeCamera.position.addScaledVector(right.current, speed);
    activeCamera.position.x = MathUtils.clamp(activeCamera.position.x, -5.25, 4.1);
    activeCamera.position.z = MathUtils.clamp(activeCamera.position.z, -3.25, 4.55);
    activeCamera.position.y = 1.65;
  });

  return <PointerLockControls makeDefault />;
}

export function SceneViewer({ sceneUrl, progress }: SceneViewerProps) {
  const [mode, setMode] = useState<"orbit" | "walk">("orbit");
  const [preset, setPreset] = useState<keyof typeof presets>("overview");

  return (
    <section className="relative h-full overflow-hidden bg-[#c7d0cc]" aria-label="Interactive 3D room">
      <Canvas shadows camera={{ position: [2.58, 1.55, 4.47], fov: 48 }}>
        <color attach="background" args={["#c7d0cc"]} />
        <fog attach="fog" args={["#c7d0cc", 10, 22]} />
        <ambientLight intensity={2.2} />
        <hemisphereLight intensity={1.8} color="#fff3dd" groundColor="#68736d" />
        <directionalLight castShadow intensity={3.4} position={[2, 5, 4]} shadow-mapSize={[2048, 2048]} />
        <Suspense fallback={<ModelLoading />}><Room key={sceneUrl ?? "sample"} sceneUrl={sceneUrl ?? "/models/classroom.glb?v=4"} /></Suspense>
        {mode === "orbit" ? (
          <><CameraPosition preset={preset} /><OrbitControls makeDefault target={presets[preset].target} minDistance={2.3} maxDistance={13} maxPolarAngle={Math.PI / 2.04} /></>
        ) : <WalkController />}
      </Canvas>

      <header className="absolute left-4 right-4 top-4 flex items-center rounded-2xl border border-white/40 bg-[#f7f4ed]/90 px-4 py-3 shadow-xl backdrop-blur-xl">
        <div><p className="text-[11px] font-bold uppercase tracking-[.11em] text-[#6e7770]">Current scene</p><h2 className="font-serif text-lg">Classroom interior tour</h2></div>
        <span className="ml-auto flex items-center gap-2 text-sm"><i className="size-2 rounded-full bg-emerald-700 ring-4 ring-emerald-700/10" />{sceneUrl ? "Generated scene" : "Sample scene"}</span>
      </header>

      <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border border-white/20 bg-[#17221c]/85 p-1.5 text-white shadow-xl backdrop-blur-xl">
        <Button onClick={() => setMode("orbit")} size="sm" className={mode === "orbit" ? "rounded-full bg-white text-[#17221c] hover:bg-white/90" : "rounded-full bg-transparent text-white hover:bg-white/10 hover:text-white"}><Rotate3D />Orbit</Button>
        <Button onClick={() => setMode("walk")} size="sm" className={mode === "walk" ? "rounded-full bg-white text-[#17221c] hover:bg-white/90" : "rounded-full bg-transparent text-white hover:bg-white/10 hover:text-white"}><Footprints />Walk</Button>
        <Button onClick={() => { setMode("orbit"); setPreset("overview"); }} size="icon-sm" variant="ghost" className="rounded-full text-white hover:bg-white/10 hover:text-white" aria-label="Fit scene"><Box /></Button>
      </div>

      <div className="absolute bottom-4 left-4 flex gap-1 rounded-xl bg-[#f7f4ed]/90 p-1 shadow-lg backdrop-blur-xl">
        {(["entry", "desks"] as const).map((name) => <Button key={name} onClick={() => { setMode("orbit"); setPreset(name); }} size="sm" variant="ghost" className="capitalize">{name}</Button>)}
      </div>

      {mode === "walk" && !progress && <div className="pointer-events-none absolute inset-x-0 top-24 mx-auto w-fit rounded-full bg-[#17221c]/80 px-4 py-2 text-xs text-white backdrop-blur">Click the room, then use WASD · Esc releases the cursor</div>}

      {progress && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[#17221c]/35 backdrop-blur-[2px]">
          <div className="w-[min(380px,calc(100%-32px))] rounded-2xl border border-white/45 bg-[#fbf8f1]/95 p-5 shadow-2xl">
            <div className="flex items-center gap-3"><LoaderCircle className="size-5 animate-spin text-[#1d513a]" /><strong className="font-serif text-lg">Updating your room</strong></div>
            <p className="mt-3 text-sm text-[#657069]">{progress.label}</p>
            <p className="mt-1 text-xs text-[#858c87]">The current scene stays available until the new version is ready.</p>
          </div>
        </div>
      )}
    </section>
  );
}

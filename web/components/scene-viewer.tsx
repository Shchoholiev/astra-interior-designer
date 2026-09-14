"use client";

import { Bounds, OrbitControls, useBounds, useGLTF } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Box, Camera, LoaderCircle, Rotate3D } from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Box3, PerspectiveCamera, Vector3 } from "three";

import { Button } from "@/components/ui/button";
import { captureRenderView, fingerprintScene, type RenderViewContext } from "@/lib/render-view";

type SceneViewerProps = {
  sceneUrl: string | null;
  progress: { label: string } | null;
  title?: string | null;
  onRenderView?: (context: RenderViewContext) => void;
};

type ViewCapture = { sceneUrl: string; capture: () => RenderViewContext };

function Room({ sceneUrl, fitVersion, onCaptureReady }: { sceneUrl: string; fitVersion: number; onCaptureReady: (capture: ViewCapture | null) => void }) {
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
      <OrbitControls makeDefault minDistance={radius * 0.05} maxDistance={radius * 12} maxPolarAngle={Math.PI / 2.04} />
      <Bounds margin={1.35} maxDuration={0}>
        <FitScene bounds={bounds} fitVersion={fitVersion} />
      </Bounds>
    </>
  );
}

function FitScene({ bounds, fitVersion }: { bounds: Box3; fitVersion: number }) {
  const api = useBounds();
  const { size, controls } = useThree();
  useEffect(() => {
    if (!controls || !("target" in controls)) return;
    api.refresh(bounds);
    const { center, distance } = api.getSize();
    const position = center.clone().addScaledVector(new Vector3(1, 1.25, 1).normalize(), distance);
    api.moveTo(position).lookAt({ target: center }).clip();
  }, [api, bounds, fitVersion, size.width, size.height, controls]);
  return null;
}

export function SceneViewer({ sceneUrl, progress, title, onRenderView }: SceneViewerProps) {
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
        <ambientLight intensity={2.2} />
        <hemisphereLight intensity={1.8} color="#fff3dd" groundColor="#68736d" />
        <directionalLight castShadow intensity={3.4} position={[2, 5, 4]} shadow-mapSize={[2048, 2048]} shadow-normalBias={0.02} />
        {sceneUrl && <Suspense fallback={null}><Room key={sceneUrl} sceneUrl={sceneUrl} fitVersion={fitVersion} onCaptureReady={setViewCapture} /></Suspense>}
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
        <span className="flex items-center gap-2 px-3 py-1.5 text-sm"><Rotate3D className="size-4" />Orbit</span>
        <Button onClick={() => setFitVersion((value) => value + 1)} size="icon-sm" variant="ghost" className="rounded-full text-white hover:bg-white/10 hover:text-white" aria-label="Fit scene"><Box /></Button>
      </div>}

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

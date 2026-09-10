"use client";

import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  type ThreadAssistantMessagePart,
  type ToolCallMessagePart,
  useLocalRuntime,
} from "@assistant-ui/react";
import { Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { SceneViewer } from "@/components/scene-viewer";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { AstraApi, latestUserInput, type AstraEvent } from "@/lib/astra-api";
import { AstraAttachmentAdapter } from "@/lib/astra-attachment-adapter";
import { PrototypeAttachmentAdapter } from "@/lib/prototype-attachment-adapter";

const backendEnabled = process.env.NEXT_PUBLIC_ASTRA_BACKEND_ENABLED === "true";

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Cancelled", "AbortError"));
    });
  });

function progressFor(event: AstraEvent) {
  const item = event.data.item;
  if (!item || typeof item !== "object") return null;
  const record = item as Record<string, unknown>;
  const name = String(record.name ?? record.tool_name ?? record.type ?? "");
  if (name.includes("execute_blender_code")) return "Blender is updating the scene";
  if (name.includes("viewport_screenshot")) return "Reviewing the room";
  if (name.includes("scene_info") || name.includes("object_info")) return "Inspecting the current scene";
  if (name.includes("addon_status")) return "Checking Blender";
  return name.includes("mcp") ? "Working in Blender" : null;
}

function toolPart(item: Record<string, unknown>): ToolCallMessagePart | null {
  if (item.type !== "mcp_call" || typeof item.id !== "string" || typeof item.name !== "string") return null;
  const finished = item.status !== "in_progress";
  return {
    type: "tool-call",
    toolCallId: item.id,
    toolName: item.name,
    args: {},
    argsText: "{}",
    ...(finished ? { result: { status: item.status }, isError: Boolean(item.error) } : {}),
  };
}

export default function Home() {
  const [progress, setProgress] = useState<{ label: string } | null>(null);
  const [sceneUrl, setSceneUrl] = useState<string | null>(null);
  const api = useMemo(() => new AstraApi(), []);
  const liveAttachments = useMemo(() => new AstraAttachmentAdapter(api), [api]);

  useEffect(() => {
    if (!backendEnabled) return;
    let active = true;
    api.getSession().then((session) => {
      if (active) setSceneUrl(session.scene_url);
    }).catch(() => {
      // The first message surfaces configuration and connection errors in chat.
    });
    return () => { active = false; };
  }, [api]);

  const adapter = useMemo<ChatModelAdapter>(() => ({
    async *run({ messages, abortSignal }) {
      if (!backendEnabled) {
        const stages = [
          "Reading your request",
          "Planning the layout",
          "Updating the room",
          "Exporting the scene",
          "Preparing the viewer",
        ] as const;
        try {
          for (const label of stages) {
            setProgress({ label });
            yield { content: [{ type: "text", text: `${label}…` }] };
            await sleep(620, abortSignal);
          }
          yield { content: [{ type: "text", text: "The room is ready. This demo keeps the sample classroom visible; enable the backend to load the generated GLB." }] };
        } finally {
          setProgress(null);
        }
        return;
      }

      const input = latestUserInput(messages);
      const messageId = input.id.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 128);
      const attachmentKeys = liveAttachments.keysFor(input.attachmentIds);
      const text = input.text || "Use the attached files to update the room.";
      let output = "";
      const tools = new Map<string, ToolCallMessagePart>();
      const content = (): ThreadAssistantMessagePart[] => [
        ...tools.values(),
        ...(output ? [{ type: "text" as const, text: output }] : []),
      ];
      const cancel = () => { void api.cancel(); };
      abortSignal.addEventListener("abort", cancel, { once: true });
      setProgress({ label: "Starting the design session" });

      try {
        for await (const event of api.sendMessage(messageId, text, attachmentKeys, abortSignal)) {
          if (event.event === "astra.error") {
            throw new Error(typeof event.data.detail === "string" ? event.data.detail : "Generation failed.");
          }
          const label = progressFor(event);
          if (label) setProgress({ label });
          const item = event.data.item;
          if (
            (event.event === "session.turn.item.added" || event.event === "session.turn.item.done")
            && item && typeof item === "object"
          ) {
            const part = toolPart(item as Record<string, unknown>);
            if (part) {
              tools.set(part.toolCallId, part);
              yield { content: content() };
            }
          }
          if (event.event === "session.turn.output_text.delta" && typeof event.data.delta === "string") {
            output += event.data.delta;
            yield { content: content() };
          } else if (event.event === "session.turn.output_text.done" && typeof event.data.text === "string") {
            output = event.data.text;
            yield { content: content() };
          }
        }
        setProgress({ label: "Loading the generated scene" });
        const session = await api.getSession();
        setSceneUrl(session.scene_url);
        if (!output) {
          output = "The room update is complete.";
          yield { content: content() };
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        output = error instanceof Error
          ? `I couldn't complete this generation: ${error.message}`
          : "I couldn't complete this generation.";
        yield {
          content: content(),
          status: { type: "incomplete", reason: "error" },
        };
      } finally {
        abortSignal.removeEventListener("abort", cancel);
        setProgress(null);
      }
    },
  }), [api, liveAttachments]);

  const runtime = useLocalRuntime(adapter, {
    initialMessages: [
      {
        role: "assistant",
        content: [
          {
            type: "text",
            text: backendEnabled
              ? "Upload a floor plan or room photo, then describe the room you want me to create."
              : "Upload a floor plan or room photo, then describe what you want to change. This demo uses a detailed CC0 classroom so you can try orbit views and a first-person tour now.",
          },
        ],
      },
    ],
    adapters: {
      attachments: backendEnabled ? liveAttachments : new PrototypeAttachmentAdapter(),
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <main className="h-dvh bg-[#17221c] p-2 text-[#18231d] md:p-3">
        <ResizablePanelGroup orientation="horizontal" className="overflow-hidden rounded-3xl">
          <ResizablePanel defaultSize="34%" minSize="26%" maxSize="46%" className="bg-[#f5f1e9]">
            <section className="flex h-full min-w-0 flex-col">
              <header className="flex h-[74px] shrink-0 items-center gap-3 border-b border-[#ddd6ca] px-5">
                <span className="grid size-9 place-items-center rounded-xl bg-[#193d2e] text-[#f6f1e8]">
                  <Sparkles className="size-4" />
                </span>
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[.12em] text-[#747a73]">Astra studio</p>
                  <h1 className="font-serif text-lg leading-tight">Interior designer</h1>
                </div>
                <span className="ml-auto rounded-full border border-[#d7cfc2] px-2 py-1 text-[11px] text-[#6f756f]">{backendEnabled ? "Connected" : "Demo"}</span>
              </header>
              <ChatPanel />
            </section>
          </ResizablePanel>

          <ResizableHandle withHandle className="bg-[#17221c]" />

          <ResizablePanel defaultSize="66%" minSize="45%">
            <SceneViewer sceneUrl={sceneUrl} progress={progress} />
          </ResizablePanel>
        </ResizablePanelGroup>
      </main>
    </AssistantRuntimeProvider>
  );
}

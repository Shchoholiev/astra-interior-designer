"use client";

import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  type ThreadAssistantMessagePart,
  type ThreadMessageLike,
  type ToolCallMessagePart,
  useLocalRuntime,
} from "@assistant-ui/react";
import { LoaderCircle, Plus, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { SceneViewer } from "@/components/scene-viewer";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  AstraApi,
  latestUserInput,
  type AstraEvent,
  type AstraMessage,
  type AstraSession,
  type AstraSessionReference,
} from "@/lib/astra-api";
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

function messageText(content: unknown) {
  if (typeof content === "string") return content;
  if (!content || typeof content !== "object") return "";
  const record = content as Record<string, unknown>;
  if (typeof record.text === "string") return record.text;
  if (!Array.isArray(record.content)) return "";
  return record.content
    .map((part) => {
      if (!part || typeof part !== "object") return "";
      const value = part as Record<string, unknown>;
      return typeof value.text === "string" ? value.text : "";
    })
    .filter(Boolean)
    .join("\n");
}

function savedMessage(message: AstraMessage): ThreadMessageLike | null {
  const content = message.content;
  const record = content && typeof content === "object" ? content as Record<string, unknown> : null;
  const tool = record ? toolPart(record) : null;
  if (tool) {
    return {
      id: message.message_id,
      role: "assistant",
      content: [tool],
      createdAt: new Date(message.created_at),
    };
  }
  const text = messageText(content);
  if (!text || (message.role !== "user" && message.role !== "assistant")) return null;
  return {
    id: message.message_id,
    role: message.role,
    content: text,
    createdAt: new Date(message.created_at),
  };
}

function initialMessages(session: AstraSession | null): ThreadMessageLike[] {
  const history = session?.messages.map(savedMessage).filter((message): message is ThreadMessageLike => Boolean(message)) ?? [];
  if (history.length) return history;
  return [{
    role: "assistant",
    content: "Upload a floor plan or room photo, then describe the room you want me to create.",
  }];
}

function sessionLabel(session: AstraSessionReference) {
  return `${session.title || "Untitled room"} · ${session.session_id.slice(-6)}`;
}

type WorkspaceProps = {
  initialSession: AstraSession | null;
  sessions: AstraSessionReference[];
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onSessionUpdated: (session: AstraSession) => void;
};

function SessionWorkspace({ initialSession, sessions, onSelectSession, onNewSession, onSessionUpdated }: WorkspaceProps) {
  const sessionId = initialSession?.session_id ?? null;
  const [progress, setProgress] = useState<{ label: string } | null>(null);
  const [sceneUrl, setSceneUrl] = useState<string | null>(initialSession?.scene_url ?? null);
  const api = useMemo(() => new AstraApi(sessionId), [sessionId]);
  const liveAttachments = useMemo(() => new AstraAttachmentAdapter(api), [api]);

  const adapter = useMemo<ChatModelAdapter>(() => ({
    async *run({ messages, abortSignal }) {
      if (!backendEnabled) {
        try {
          for (const label of ["Reading your request", "Planning the layout", "Updating the room", "Exporting the scene"] as const) {
            setProgress({ label });
            yield { content: [{ type: "text", text: `${label}…` }] };
            await sleep(620, abortSignal);
          }
          yield { content: [{ type: "text", text: "The request is ready for the Blender backend." }] };
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
      const preparationId = "astra-sandbox-preparation";
      const content = (): ThreadAssistantMessagePart[] => [
        ...tools.values(),
        ...(output ? [{ type: "text" as const, text: output }] : []),
      ];
      const cancel = () => { void api.cancel(); };
      abortSignal.addEventListener("abort", cancel, { once: true });
      setProgress({ label: "Starting the design session" });

      try {
        for await (const event of api.sendMessage(messageId, text, attachmentKeys, abortSignal)) {
          const eventName = event.event.startsWith("agent.")
            ? event.event.slice("agent.".length)
            : event.event;
          if (event.event === "astra.error") {
            throw new Error(typeof event.data.detail === "string" ? event.data.detail : "Generation failed.");
          }
          if (event.event === "astra.progress") {
            const label = typeof event.data.label === "string"
              ? event.data.label
              : "Preparing the Blender sandbox";
            setProgress({ label });
            tools.set(preparationId, {
              type: "tool-call",
              toolCallId: preparationId,
              toolName: "prepare_blender_sandbox",
              args: {},
              argsText: "{}",
            });
            yield { content: content() };
            continue;
          }
          const preparation = tools.get(preparationId);
          if (preparation && preparation.result === undefined) {
            tools.set(preparationId, {
              ...preparation,
              result: { status: "completed" },
            });
          }
          const label = progressFor(event);
          if (label) setProgress({ label });
          const item = event.data.item;
          if (
            (eventName === "session.turn.item.added" || eventName === "session.turn.item.done")
            && item && typeof item === "object"
          ) {
            const part = toolPart(item as Record<string, unknown>);
            if (part) {
              tools.set(part.toolCallId, part);
              yield { content: content() };
            }
          }
          if (eventName === "session.turn.output_text.delta" && typeof event.data.delta === "string") {
            output += event.data.delta;
            yield { content: content() };
          } else if (eventName === "session.turn.output_text.done" && typeof event.data.text === "string") {
            output = event.data.text;
            yield { content: content() };
          }
        }
        setProgress({ label: "Loading the generated scene" });
        const updated = await api.getSession();
        setSceneUrl(updated.scene_url);
        onSessionUpdated(updated);
        if (!output) {
          output = "The room update is complete.";
          yield { content: content() };
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const preparation = tools.get(preparationId);
        if (preparation && preparation.result === undefined) {
          tools.set(preparationId, {
            ...preparation,
            result: { status: "failed" },
            isError: true,
          });
        }
        output = error instanceof Error
          ? `I couldn't complete this generation: ${error.message}`
          : "I couldn't complete this generation.";
        yield { content: content(), status: { type: "incomplete", reason: "error" } };
      } finally {
        abortSignal.removeEventListener("abort", cancel);
        setProgress(null);
      }
    },
  }), [api, liveAttachments, onSessionUpdated]);

  const runtime = useLocalRuntime(adapter, {
    initialMessages: initialMessages(initialSession),
    adapters: { attachments: backendEnabled ? liveAttachments : new PrototypeAttachmentAdapter() },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <main className="h-dvh bg-[#17221c] p-2 text-[#18231d] md:p-3">
        <ResizablePanelGroup orientation="horizontal" className="overflow-hidden rounded-3xl">
          <ResizablePanel defaultSize="34%" minSize="26%" maxSize="46%" className="bg-[#f5f1e9]">
            <section className="flex h-full min-w-0 flex-col">
              <header className="flex h-[74px] shrink-0 items-center gap-3 border-b border-[#ddd6ca] px-5">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#193d2e] text-[#f6f1e8]"><Sparkles className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-bold uppercase tracking-[.12em] text-[#747a73]">Astra studio</p>
                  {backendEnabled ? (
                    <select aria-label="Current design session" className="block w-full truncate bg-transparent font-serif text-lg leading-tight outline-none" value={sessionId ?? ""} onChange={(event) => onSelectSession(event.target.value)}>
                      {sessions.map((item) => <option key={item.session_id} value={item.session_id}>{sessionLabel(item)}</option>)}
                    </select>
                  ) : <h1 className="font-serif text-lg leading-tight">Interior designer</h1>}
                </div>
                {backendEnabled && <Button onClick={onNewSession} size="icon-sm" variant="outline" className="shrink-0 rounded-full" aria-label="Start a new room"><Plus /></Button>}
                <span className="rounded-full border border-[#d7cfc2] px-2 py-1 text-[11px] text-[#6f756f]">{backendEnabled ? "Connected" : "Demo"}</span>
              </header>
              <ChatPanel />
            </section>
          </ResizablePanel>
          <ResizableHandle withHandle className="bg-[#17221c]" />
          <ResizablePanel defaultSize="66%" minSize="45%">
            <SceneViewer sceneUrl={sceneUrl} progress={progress} title={initialSession?.title} />
          </ResizablePanel>
        </ResizablePanelGroup>
      </main>
    </AssistantRuntimeProvider>
  );
}

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<AstraSession | null>(null);
  const [sessions, setSessions] = useState<AstraSessionReference[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!backendEnabled) return;
    let active = true;
    const load = async () => {
      let available = await AstraApi.listSessions();
      let sessionId = activeSessionId ?? AstraApi.activeSessionId();
      if (!sessionId || !available.some((item) => item.session_id === sessionId)) {
        sessionId = available[0]?.session_id ?? await AstraApi.createSession("New room");
        if (!available.some((item) => item.session_id === sessionId)) {
          available = await AstraApi.listSessions();
        }
      }
      AstraApi.selectSession(sessionId);
      const loaded = await new AstraApi(sessionId).getSession();
      if (!active) return;
      setSession(loaded);
      setActiveSessionId(loaded.session_id);
      setSessions(available);
      setLoadError(null);
    };
    load().catch((error) => {
      if (active) setLoadError(error instanceof Error ? error.message : "Unable to load the session.");
    });
    return () => { active = false; };
  }, [activeSessionId]);

  const selectSession = (sessionId: string) => {
    if (!sessionId || sessionId === activeSessionId) return;
    AstraApi.selectSession(sessionId);
    setSession(null);
    setActiveSessionId(sessionId);
  };

  const newSession = async () => {
    try {
      const sessionId = await AstraApi.createSession("New room");
      setSessions(await AstraApi.listSessions());
      setSession(null);
      setActiveSessionId(sessionId);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Unable to create a session.");
    }
  };

  const updateSession = (updated: AstraSession) => {
    setSession(updated);
    void AstraApi.listSessions().then(setSessions);
  };

  if (backendEnabled && (!session || session.session_id !== activeSessionId)) {
    return (
      <main className="grid h-dvh place-items-center bg-[#17221c] text-[#f5f1e9]">
        <div className="flex items-center gap-3 text-sm"><LoaderCircle className="size-5 animate-spin" /><span>{loadError ?? "Opening your design session…"}</span></div>
      </main>
    );
  }

  return (
    <SessionWorkspace
      key={activeSessionId ?? "demo"}
      initialSession={session}
      sessions={sessions}
      onSelectSession={selectSession}
      onNewSession={newSession}
      onSessionUpdated={updateSession}
    />
  );
}

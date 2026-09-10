"use client";

import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  type CompleteAttachment,
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
import { renderViewMessage } from "@/lib/render-view";
import { followTurn, TurnConnectionError } from "@/lib/follow-turn";
import { toolPart, TurnTranscript } from "@/lib/turn-transcript";

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
  const attachments: CompleteAttachment[] = message.role === "user"
    ? (message.attachment_keys ?? []).map((key) => ({
        id: key,
        // Upload keys use inputs/<uuid>-<filename>. Keep the original filename,
        // but don't invent a public URL for the private S3 object.
        name: key.split("/").pop()!.replace(/^[a-f0-9]{32}-/i, ""),
        type: "file",
        status: { type: "complete" },
        content: [],
      }))
    : [];
  if ((!text && !attachments.length) || (message.role !== "user" && message.role !== "assistant")) return null;
  return {
    id: message.message_id,
    role: message.role,
    content: text,
    ...(message.role === "user" ? { attachments } : {}),
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
  const [render, setRender] = useState<{ url: string; sha256: string | null } | null>(initialSession?.render_url ? { url: initialSession.render_url, sha256: initialSession.render_sha256 ?? null } : null);
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
      const transcript = new TurnTranscript();
      const preparationId = "astra-sandbox-preparation";
      let preparation: ToolCallMessagePart | undefined;
      let updated: AstraSession | undefined;
      let terminalStatus = "completed";
      setProgress({ label: "Starting the design session" });

      try {
        for await (const event of followTurn({
          stream: () => api.sendMessage(messageId, text, attachmentKeys, abortSignal),
          snapshot: () => api.getSession(abortSignal),
          messageId, signal: abortSignal,
        })) {
          if (event.event === "astra.recovering") {
            setProgress({ label: String(event.data.label) });
            continue;
          }
          if (event.event === "astra.snapshot") {
            updated = event.data.session as AstraSession;
            transcript.restore(updated.messages, messageId);
            if (preparation && preparation.result === undefined && updated.messages.some((item) => item.message_id === messageId)) {
              preparation = { ...preparation, result: { status: "completed" } };
              transcript.setTool(preparation);
            }
            yield { content: transcript.content() };
            continue;
          }
          if (event.event === "astra.finished") {
            terminalStatus = String(event.data.status);
            continue;
          }
          if (event.event === "astra.progress") {
            const label = typeof event.data.label === "string"
              ? event.data.label
              : "Preparing the Blender sandbox";
            setProgress({ label });
            preparation = {
              type: "tool-call",
              toolCallId: preparationId,
              toolName: "prepare_blender_sandbox",
              args: {},
              argsText: "{}",
            };
            transcript.setTool(preparation);
            yield { content: transcript.content() };
            continue;
          }
          if (preparation && preparation.result === undefined) {
            preparation = {
              ...preparation,
              result: { status: "completed" },
            };
            transcript.setTool(preparation);
          }
          const label = progressFor(event);
          if (label) setProgress({ label });
          transcript.apply(event);
          yield { content: transcript.content() };
        }
        if (updated) {
          setSceneUrl(updated.scene_url);
          setRender(updated.render_url ? { url: updated.render_url, sha256: updated.render_sha256 ?? null } : null);
          onSessionUpdated(updated);
        }
        if (terminalStatus !== "completed") {
          transcript.note("turn-outcome", terminalStatus === "cancelled" ? "Generation was cancelled." : "The backend reported that this turn failed.");
          yield { content: transcript.content(), status: { type: "incomplete", reason: terminalStatus === "cancelled" ? "cancelled" : "error" } };
        } else {
          if (!transcript.content().some((part) => part.type === "text")) transcript.note("turn-outcome", "The turn is complete.");
          yield { content: transcript.content() };
        }
      } catch (error) {
        if (abortSignal.aborted) return;
        if (!(error instanceof TurnConnectionError) && preparation && preparation.result === undefined) {
          transcript.setTool({
            ...preparation,
            result: { status: "failed" },
            isError: true,
          });
        }
        transcript.note("turn-error", error instanceof Error ? error.message : "Unable to follow this turn. Refresh the session to check its status.");
        yield { content: transcript.content(), status: { type: "incomplete", reason: "error" } };
      } finally {
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
              <ChatPanel render={render} onCancel={backendEnabled ? () => { void api.cancel(); } : undefined} />
            </section>
          </ResizablePanel>
          <ResizableHandle withHandle className="bg-[#17221c]" />
          <ResizablePanel defaultSize="66%" minSize="45%">
            <SceneViewer sceneUrl={sceneUrl} progress={progress} title={initialSession?.title} onRenderView={backendEnabled ? (context) => {
              if (runtime.thread.getState().isRunning) return;
              runtime.thread.append({ role: "user", content: [{ type: "text", text: renderViewMessage(context) }] });
            } : undefined} />
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

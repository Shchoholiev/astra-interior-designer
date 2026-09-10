"use client";

import {
  AttachmentPrimitive,
  AuiIf,
  ComposerPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { ArrowDown, ArrowUp, Check, ImagePlus, LoaderCircle, Square, TriangleAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RENDER_VIEW_CONTEXT_MARKER } from "@/lib/render-view";

function AttachmentTile({ removable = false }: { removable?: boolean }) {
  return (
    <AttachmentPrimitive.Root className="flex max-w-44 items-center gap-2 overflow-hidden rounded-lg border border-[#d8d1c5] bg-[#fffdf8] p-2 text-xs">
      <AttachmentPrimitive.unstable_Thumb className="size-9 shrink-0 overflow-hidden rounded-md bg-[#e8e2d7] object-cover" />
      <span className="truncate"><AttachmentPrimitive.Name /></span>
      {removable && (
        <AttachmentPrimitive.Remove asChild>
          <Button size="icon-xs" variant="ghost" aria-label="Remove attachment"><X /></Button>
        </AttachmentPrimitive.Remove>
      )}
    </AttachmentPrimitive.Root>
  );
}

function ChatMessage() {
  const role = useAuiState((state) => state.message.role);
  return (
    <MessagePrimitive.Root className={role === "user" ? "ml-auto max-w-[88%]" : "mr-auto max-w-[92%]"}>
      <MessagePrimitive.Attachments>
        {() => <AttachmentTile />}
      </MessagePrimitive.Attachments>
      <div className={role === "user" ? "rounded-2xl rounded-br-md bg-[#193d2e] px-4 py-3 text-[#faf7f0]" : "rounded-2xl rounded-tl-md border border-[#ddd6ca] bg-[#fffdf8] px-4 py-3 text-[#34423a] shadow-sm"}>
        {role === "assistant" && <p className="mb-1 text-[10px] font-bold uppercase tracking-[.12em] text-[#788078]">Astra</p>}
        <MessagePrimitive.Parts>
          {({ part }) => {
            if (role === "user" && part.type === "text" && part.text.includes(RENDER_VIEW_CONTEXT_MARKER)) {
              const index = part.text.indexOf(RENDER_VIEW_CONTEXT_MARKER);
              return <>
                <p className="whitespace-pre-wrap text-[15px] leading-6">{part.text.slice(0, index).trim()}</p>
                <details className="mt-3 text-xs">
                  <summary className="cursor-pointer">Camera and scene details</summary>
                  <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all">{part.text.slice(index)}</pre>
                </details>
              </>;
            }
            if (part.type === "text") return <MessagePartPrimitive.Text className="whitespace-pre-wrap text-[15px] leading-6" />;
            if (part.type !== "tool-call") return null;
            const running = part.result === undefined && !part.isError;
            const labels: Record<string, string> = {
              get_scene_info: "Inspecting the Blender scene",
              get_object_info: "Inspecting scene objects",
              get_viewport_screenshot: "Reviewing the room",
              execute_blender_code: "Updating the room in Blender",
              get_addon_status: "Checking Blender",
              prepare_blender_sandbox: "Connecting the Blender sandbox",
            };
            return (
              <div className="my-2 flex items-center gap-2 rounded-xl border border-[#d8d1c5] bg-[#f5f1e9] px-3 py-2 text-sm text-[#526057]">
                {running ? <LoaderCircle className="size-4 animate-spin text-[#1d513a]" /> : part.isError ? <TriangleAlert className="size-4 text-red-700" /> : <Check className="size-4 text-emerald-700" />}
                <span>{labels[part.toolName] ?? part.toolName.replaceAll("_", " ")}</span>
                <span className="ml-auto text-[10px] font-bold uppercase tracking-wide text-[#899087]">{running ? "Running" : part.isError ? "Failed" : "Done"}</span>
              </div>
            );
          }}
        </MessagePrimitive.Parts>
      </div>
    </MessagePrimitive.Root>
  );
}

export function ChatPanel({ onCancel }: { onCancel?: () => void }) {
  return (
    <ThreadPrimitive.Root className="relative flex min-h-0 flex-1 flex-col bg-[#f5f1e9]">
      <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pt-5">
        <div className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-5">
          <ThreadPrimitive.Messages>{() => <ChatMessage />}</ThreadPrimitive.Messages>
        </div>

        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mx-auto mt-6 w-full max-w-xl bg-gradient-to-t from-[#f5f1e9] via-[#f5f1e9] to-transparent pb-4 pt-8">
          <ThreadPrimitive.ScrollToBottom asChild>
            <Button size="icon-sm" variant="outline" className="absolute -top-1 left-1/2 -translate-x-1/2 rounded-full" aria-label="Scroll to latest message"><ArrowDown /></Button>
          </ThreadPrimitive.ScrollToBottom>

          <ComposerPrimitive.Root className="rounded-2xl border border-[#d8d1c5] bg-[#fffdf8] p-2 shadow-[0_16px_45px_rgb(35_45_39/10%)]">
            <ComposerPrimitive.Attachments>
              {() => <AttachmentTile removable />}
            </ComposerPrimitive.Attachments>
            <ComposerPrimitive.Input rows={2} maxRows={6} placeholder="Describe your room or ask for a change…" className="w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-6 outline-none placeholder:text-[#92968f]" />
            <div className="flex items-center gap-2">
              <ComposerPrimitive.AddAttachment asChild>
                <Button size="sm" variant="ghost"><ImagePlus />Add image</Button>
              </ComposerPrimitive.AddAttachment>
              <span className="text-[11px] text-[#8b9089]">25 MB max</span>
              <div className="ml-auto">
                <AuiIf condition={(state) => !state.thread.isRunning}>
                  <ComposerPrimitive.Send asChild><Button size="icon" className="rounded-xl" aria-label="Send message"><ArrowUp /></Button></ComposerPrimitive.Send>
                </AuiIf>
                <AuiIf condition={(state) => state.thread.isRunning}>
                  <ComposerPrimitive.Cancel asChild><Button onClick={onCancel} size="icon" className="rounded-xl" aria-label="Cancel generation"><Square className="fill-current" /></Button></ComposerPrimitive.Cancel>
                </AuiIf>
              </div>
            </div>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

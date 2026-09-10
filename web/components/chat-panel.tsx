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
import { ArrowDown, ArrowUp, ImagePlus, Square, X } from "lucide-react";

import { Button } from "@/components/ui/button";

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
          {({ part }) => part.type === "text" ? <MessagePartPrimitive.Text className="whitespace-pre-wrap text-[15px] leading-6" /> : null}
        </MessagePrimitive.Parts>
      </div>
    </MessagePrimitive.Root>
  );
}

export function ChatPanel() {
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
                  <ComposerPrimitive.Cancel asChild><Button size="icon" className="rounded-xl" aria-label="Cancel generation"><Square className="fill-current" /></Button></ComposerPrimitive.Cancel>
                </AuiIf>
              </div>
            </div>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

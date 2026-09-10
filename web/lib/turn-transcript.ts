import type { ThreadAssistantMessagePart, ToolCallMessagePart } from "@assistant-ui/react";
import type { AstraEvent, AstraMessage } from "./astra-api";

export function toolPart(item: Record<string, unknown>): ToolCallMessagePart | null {
  if (typeof item.id !== "string") return null;
  const name = item.type === "mcp_call" ? item.name
    : item.type === "command_execution" ? "command_execution"
    : null;
  if (typeof name !== "string") return null;
  const finished = item.status !== "in_progress";
  return {
    type: "tool-call", toolCallId: item.id, toolName: name, args: {}, argsText: "{}",
    ...(finished ? { result: { status: item.status }, isError: Boolean(item.error) || item.status === "failed" } : {}),
  };
}

// One ordered entry per agent item; completion updates only that item's text.
// A single turn can contain many assistant messages interleaved with tools.
export class TurnTranscript {
  private items = new Map<string, Map<number, ThreadAssistantMessagePart>>();
  private seenEvents = new Set<string>();
  private finishedText = new Set<string>();

  private put(id: string, index: number, part: ThreadAssistantMessagePart) {
    if (!this.items.has(id)) this.items.set(id, new Map());
    this.items.get(id)!.set(index, part);
  }

  setTool(part: ToolCallMessagePart) { this.put(part.toolCallId, 0, part); }

  note(id: string, text: string) { this.put(id, 0, { type: "text", text }); }

  applyItem(item: Record<string, unknown>) {
    if (typeof item.id !== "string") return;
    // Reserve the position on item.added, even before its first text delta.
    if (!this.items.has(item.id) && (item.type === "message" || toolPart(item))) this.items.set(item.id, new Map());
    const tool = toolPart(item);
    if (tool) this.setTool(tool);
    if (item.type !== "message" || item.role !== "assistant" || !Array.isArray(item.content)) return;
    item.content.forEach((part, index) => {
      if (part?.type !== "output_text" || typeof part.text !== "string") return;
      if (part.text || item.status !== "in_progress") this.put(item.id as string, index, { type: "text", text: part.text });
      if (item.status !== "in_progress") this.finishedText.add(`${item.id}:${index}`);
    });
  }

  apply(event: AstraEvent) {
    const eventId = event.id ?? event.data.event_id;
    if (typeof eventId === "string") {
      if (this.seenEvents.has(eventId)) return;
      this.seenEvents.add(eventId);
    }
    const type = event.event.replace(/^agent\./, "");
    const item = event.data.item;
    if ((type === "session.turn.item.added" || type === "session.turn.item.done") && item && typeof item === "object") {
      this.applyItem(item as Record<string, unknown>);
    }
    if (type !== "session.turn.output_text.delta" && type !== "session.turn.output_text.done") return;
    const id = typeof event.data.item_id === "string" ? event.data.item_id : `output-${event.data.output_index ?? 0}`;
    const index = typeof event.data.content_index === "number" ? event.data.content_index : 0;
    const key = `${id}:${index}`;
    if (type.endsWith(".done") && typeof event.data.text === "string") {
      this.put(id, index, { type: "text", text: event.data.text });
      this.finishedText.add(key);
    } else if (!this.finishedText.has(key) && typeof event.data.delta === "string") {
      const old = this.items.get(id)?.get(index);
      this.put(id, index, { type: "text", text: (old?.type === "text" ? old.text : "") + event.data.delta });
    }
  }

  restore(messages: AstraMessage[], messageId: string) {
    const userIndex = messages.findIndex((message) => message.message_id === messageId && message.role === "user");
    if (userIndex < 0) return;
    const turnId = messages[userIndex].turn_id;
    const recovered: string[] = [];
    for (const message of messages.slice(userIndex + 1)) {
      if (message.role === "user") break;
      if (turnId && message.turn_id && message.turn_id !== turnId) continue;
      if (!message.content || typeof message.content !== "object") continue;
      const item = message.content as Record<string, unknown>;
      this.applyItem(item);
      if (typeof item.id === "string" && this.items.has(item.id)) recovered.push(item.id);
    }
    // Persisted order fills gaps missed during a disconnect; retain any newer
    // partial live items that haven't been written to history yet.
    const preparation = "astra-sandbox-preparation";
    const order = [...(this.items.has(preparation) ? [preparation] : []), ...recovered, ...this.items.keys()];
    this.items = new Map([...new Set(order)].map((id) => [id, this.items.get(id)!]));
  }

  content(): ThreadAssistantMessagePart[] {
    return [...this.items.values()].flatMap((parts) => [...parts.entries()].sort(([a], [b]) => a - b).map(([, part]) => ({ ...part })));
  }
}

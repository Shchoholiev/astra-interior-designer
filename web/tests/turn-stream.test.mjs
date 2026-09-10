import assert from "node:assert/strict";
import test from "node:test";
import { TurnTranscript } from "../lib/turn-transcript.ts";
import { followTurn, TurnConnectionError } from "../lib/follow-turn.ts";
import { AstraApi } from "../lib/astra-api.ts";

const event = (type, data, id) => ({ event: `agent.session.turn.${type}`, data, id });
const user = (status = "submitted") => ({ message_id: "user-1", role: "user", status, turn_id: "turn-1", content: { text: "Build a room" }, attachment_keys: [] });
const saved = (id, text, turn_id = "turn-1") => ({ message_id: id, role: "assistant", turn_id, content: { id, type: "message", role: "assistant", status: "completed", content: [{ type: "output_text", text }] } });
const snapshot = (status, messages = []) => ({ session_id: "session-1", sandbox_status: "running", status: status === "submitted" ? "in_progress" : "idle", messages: [user(status), ...messages], scene_url: null });
const noWait = async () => {};

test("multiple text items and tool calls remain in sequence; done replaces only its own delta", () => {
  const t = new TurnTranscript();
  t.apply(event("output_text.delta", { item_id: "first", content_index: 0, delta: "Planning" }, "e1"));
  t.apply(event("output_text.done", { item_id: "first", content_index: 0, text: "Planning the room." }, "e2"));
  t.apply(event("item.added", { item: { id: "tool", type: "mcp_call", name: "execute_blender_code", status: "in_progress" } }, "e3"));
  t.apply(event("output_text.delta", { item_id: "second", content_index: 0, delta: "Built it." }, "e4"));
  t.apply(event("output_text.delta", { item_id: "second", content_index: 0, delta: "Built it." }, "e4"));
  t.apply(event("output_text.done", { item_id: "second", content_index: 0, text: "Built it." }, "e5"));
  t.apply(event("item.done", { item: { id: "tool", type: "mcp_call", name: "execute_blender_code", status: "completed" } }, "e6"));
  assert.deepEqual(t.content().map((p) => p.type === "text" ? p.text : p.toolName), ["Planning the room.", "execute_blender_code", "Built it."]);
  assert.equal(t.content()[1].result.status, "completed");
  t.note("error", "Connection lost; status unknown.");
  assert.equal(t.content()[0].text, "Planning the room.");
});

test("recovery fills missed messages in history order without duplicates or prior-turn text", () => {
  const t = new TurnTranscript();
  t.apply(event("output_text.delta", { item_id: "last", delta: "Partial" }));
  t.restore([saved("old", "Old turn", "turn-0"), user(), saved("first", "First."), saved("last", "Finished.")], "user-1");
  t.restore([user(), saved("first", "First."), saved("last", "Finished.")], "user-1");
  assert.deepEqual(t.content().map((p) => p.text), ["First.", "Finished."]);
});

test("disconnect follows the accepted turn through polling without another POST", async () => {
  let streams = 0, reads = 0;
  const events = [];
  const t = new TurnTranscript();
  for await (const e of followTurn({
    async *stream() { streams++; yield event("output_text.done", { item_id: "first", text: "Working." }); throw new TypeError("Network error"); },
    snapshot: async () => ++reads === 1 ? snapshot("submitted", [saved("first", "Working.")]) : snapshot("completed", [saved("first", "Working."), saved("last", "Done.")]),
    messageId: "user-1", signal: new AbortController().signal, wait: noWait,
  })) {
    events.push(e);
    if (e.event === "astra.snapshot") t.restore(e.data.session.messages, "user-1"); else t.apply(e);
  }
  assert.equal(streams, 1);
  assert.equal(reads, 2);
  assert.equal(events.at(-1).data.status, "completed");
  assert.deepEqual(t.content().map((p) => p.text), ["Working.", "Done."]);
});

test("clean premature EOF is not success; a running sandbox can contain a failed turn", async () => {
  let reads = 0;
  const result = [];
  for await (const e of followTurn({
    async *stream() {}, snapshot: async () => snapshot(++reads === 1 ? "submitted" : "failed"),
    messageId: "user-1", signal: new AbortController().signal, wait: noWait,
  })) result.push(e);
  assert.equal(reads, 2);
  assert.equal(result.at(-1).data.status, "failed");
});

test("unreachable status reports uncertainty, not a generation failure", async () => {
  await assert.rejects(async () => {
    for await (const unused of followTurn({
      async *stream() { throw new TypeError("Network error"); }, snapshot: async () => { throw new TypeError("Offline"); },
      messageId: "user-1", signal: new AbortController().signal, wait: noWait,
    })) void unused;
  }, TurnConnectionError);
});

test("cancellation stops status polling without another submission", async () => {
  const controller = new AbortController();
  let reads = 0, streams = 0;
  await assert.rejects(async () => {
    for await (const unused of followTurn({
      async *stream() { streams++; }, snapshot: async () => { reads++; return snapshot("submitted"); },
      messageId: "user-1", signal: controller.signal, wait: async () => { controller.abort(); controller.signal.throwIfAborted(); },
    })) void unused;
  }, { name: "AbortError" });
  assert.equal(streams, 1);
  assert.equal(reads, 1);
});

test("session recovery reads all history pages, including turns beyond the first hundred items", async (t) => {
  t.mock.method(globalThis, "fetch", async (url) => new Response(JSON.stringify(String(url).includes("cursor=")
    ? { ...snapshot("completed"), next_cursor: null }
    : { ...snapshot("submitted"), messages: [saved("old", "Old")], next_cursor: "next page" }), { headers: { "Content-Type": "application/json" } }));
  t.mock.method(AstraApi, "selectSession", () => {});
  const session = await new AstraApi("session-1").getSession();
  assert.equal(session.messages.length, 2);
  assert.equal(session.messages.at(-1).message_id, "user-1");
  assert.equal(fetch.mock.callCount(), 2);
});

test("SSE parser handles chunk boundaries and comments preceding events", async (t) => {
  const encoder = new TextEncoder();
  t.mock.method(globalThis, "fetch", async () => new Response(new ReadableStream({ start(controller) {
    controller.enqueue(encoder.encode(': heartbeat\r\nevent: agent.session.turn.output_text.do'));
    controller.enqueue(encoder.encode('ne\r\nid: e1\r\ndata: {"item_id":"first","text":"First."}\r\n\r\n'));
    controller.close();
  } })));
  const result = [];
  for await (const e of new AstraApi("session-1").sendMessage("user-1", "Test", [], new AbortController().signal)) result.push(e);
  assert.equal(result.length, 1);
  assert.equal(result[0].data.text, "First.");
  assert.equal(result[0].id, "e1");
});

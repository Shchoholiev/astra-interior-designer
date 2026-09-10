import type { ThreadMessage } from "@assistant-ui/react";

export type AstraMessage = {
  message_id: string;
  role: string;
  content: unknown;
  status: string;
  created_at: string;
  attachment_keys: string[];
  turn_id?: string | null;
  item_id?: string | null;
};

export type AstraSession = {
  session_id: string;
  title: string | null;
  status: string;
  sandbox_status: string;
  messages: AstraMessage[];
  next_cursor: string | null;
  scene_url: string | null;
  scene_url_expires_at: string | null;
  render_url?: string | null;
  render_sha256?: string | null;
};

export type AstraEvent = { event: string; id?: string; data: Record<string, unknown> };

export class AstraHttpError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

export type AstraSessionReference = {
  session_id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

const SESSION_KEY = "astra-session-id";

async function errorMessage(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export function latestUserInput(messages: readonly ThreadMessage[]) {
  const message = [...messages].reverse().find((candidate) => candidate.role === "user");
  if (!message || message.role !== "user") throw new Error("A user message is required.");
  const text = message.content
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n")
    .trim();
  return { id: message.id, text, attachmentIds: message.attachments.map(({ id }) => id) };
}

export class AstraApi {
  private sessionId: string | null = null;
  private sessionPromise: Promise<string> | null = null;

  constructor(sessionId?: string | null) {
    this.sessionId = sessionId ?? null;
  }

  static activeSessionId() {
    return window.localStorage.getItem(SESSION_KEY);
  }

  static selectSession(sessionId: string) {
    window.localStorage.setItem(SESSION_KEY, sessionId);
  }

  static async createSession(title = "New room") {
    const response = await fetch("/api/astra/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    const { session_id } = (await response.json()) as { session_id: string };
    AstraApi.selectSession(session_id);
    return session_id;
  }

  static async listSessions() {
    const response = await fetch("/api/astra/sessions", { cache: "no-store" });
    if (!response.ok) throw new Error(await errorMessage(response));
    return (await response.json()) as AstraSessionReference[];
  }

  async ensureSession() {
    if (this.sessionId) return this.sessionId;
    if (this.sessionPromise) return this.sessionPromise;
    this.sessionPromise = this.loadOrCreateSession();
    try {
      this.sessionId = await this.sessionPromise;
      return this.sessionId;
    } finally {
      this.sessionPromise = null;
    }
  }

  private async loadOrCreateSession() {
    const saved = window.localStorage.getItem(SESSION_KEY);
    if (saved) {
      const response = await fetch(`/api/astra/sessions/${encodeURIComponent(saved)}`, {
        cache: "no-store",
      });
      if (response.ok) return saved;
      if (response.status !== 404) throw new Error(await errorMessage(response));
      window.localStorage.removeItem(SESSION_KEY);
    }
    const sessions = await AstraApi.listSessions();
    if (sessions[0]) {
      AstraApi.selectSession(sessions[0].session_id);
      return sessions[0].session_id;
    }
    return AstraApi.createSession();
  }

  async getSession(signal?: AbortSignal) {
    const sessionId = await this.ensureSession();
    let session: AstraSession | undefined;
    let cursor: string | null = null;
    do {
      const query = new URLSearchParams({ limit: "100" });
      if (cursor) query.set("cursor", cursor);
      const response = await fetch(`/api/astra/sessions/${encodeURIComponent(sessionId)}?${query}`, {
        cache: "no-store", signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const page = await response.json() as AstraSession;
      session = session ? { ...page, messages: [...session.messages, ...page.messages] } : page;
      cursor = page.next_cursor;
    } while (cursor);
    AstraApi.selectSession(sessionId);
    return session;
  }

  async createUpload(filename: string, contentType: string) {
    const sessionId = await this.ensureSession();
    const response = await fetch(
      `/api/astra/sessions/${encodeURIComponent(sessionId)}/files/upload-url`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, content_type: contentType }),
      },
    );
    if (!response.ok) throw new Error(await errorMessage(response));
    return (await response.json()) as {
      object_key: string;
      upload_url: string;
      headers: Record<string, string>;
      expires_at: string;
    };
  }

  async cancel() {
    if (!this.sessionId) return;
    await fetch(`/api/astra/sessions/${encodeURIComponent(this.sessionId)}/cancel`, {
      method: "POST",
    });
  }

  async *sendMessage(
    messageId: string,
    text: string,
    attachmentKeys: string[],
    signal: AbortSignal,
  ): AsyncGenerator<AstraEvent> {
    const sessionId = await this.ensureSession();
    const controller = new AbortController();
    const abort = () => controller.abort(signal.reason);
    signal.throwIfAborted();
    signal.addEventListener("abort", abort, { once: true });
    let timer = setTimeout(() => controller.abort(new Error("Stream stalled")), 45000);
    const resetTimeout = () => {
      clearTimeout(timer);
      timer = setTimeout(() => controller.abort(new Error("Stream stalled")), 45000);
    };
    let reader: ReadableStreamDefaultReader<string> | undefined;
    try {
      const response = await fetch(`/api/astra/sessions/${encodeURIComponent(sessionId)}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ message_id: messageId, text, attachment_keys: attachmentKeys }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new AstraHttpError(await errorMessage(response), response.status);

      reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        resetTimeout();
        buffer += value ?? "";
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          if (!block) continue;
          let event = "message";
          let id: string | undefined;
          const data: string[] = [];
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("id:")) id = line.slice(3).trim();
            else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
          }
          if (data.length) {
            const payload = JSON.parse(data.join("\n")) as Record<string, unknown>;
            const resolvedEvent = event === "message" && typeof payload.type === "string"
              ? payload.type
              : event;
            yield { event: resolvedEvent, id, data: payload };
          }
        }
        if (done) break;
      }
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      await reader?.cancel().catch(() => {});
      reader?.releaseLock();
      controller.abort();
    }
  }
}

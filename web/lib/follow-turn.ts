import type { AstraEvent, AstraSession } from "./astra-api";

export class TurnConnectionError extends Error {}

export function waitForRetry(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}

export async function* followTurn({ stream, snapshot, messageId, signal, wait = waitForRetry }: {
  stream: () => AsyncIterable<AstraEvent>;
  snapshot: () => Promise<AstraSession>;
  messageId: string;
  signal: AbortSignal;
  wait?: (ms: number, signal: AbortSignal) => Promise<void>;
}): AsyncGenerator<AstraEvent> {
  let submissionAttempts = 0;
  while (!signal.aborted) {
    let streamError: Error | null = null;
    let backendError = false;
    try {
      for await (const event of stream()) {
        if (event.event === "astra.error") {
          backendError = true;
          throw new Error(typeof event.data.detail === "string" ? event.data.detail : "The backend could not continue the turn.");
        }
        yield event;
      }
    } catch (error) {
      if (signal.aborted) throw error;
      if (error instanceof Error && "status" in error && typeof error.status === "number"
        && error.status >= 400 && error.status < 500 && ![408, 409, 429].includes(error.status)) throw error;
      streamError = error instanceof Error ? error : new Error("Stream disconnected");
    }

    let failures = 0;
    let missing = 0;
    while (!signal.aborted) {
      yield { event: "astra.recovering", data: { label: "Checking saved turn progress…" } };
      let session: AstraSession;
      try {
        session = await snapshot();
        failures = 0;
      } catch (error) {
        if (signal.aborted) throw error;
        if (++failures >= 5) throw new TurnConnectionError("Connection lost. I couldn't confirm whether the turn finished. It was not cancelled; refresh this session to recover its progress.");
        await wait(Math.min(1000 * 2 ** failures, 10000), signal);
        continue;
      }
      yield { event: "astra.snapshot", data: { session } };
      const message = session.messages.find((item) => item.role === "user" && item.message_id === messageId);
      if (message && ["completed", "failed", "cancelled"].includes(message.status)) {
        yield { event: "astra.finished", data: { status: message.status } };
        return;
      }
      if (message) {
        // A submitted turn is independent of its SSE connection. Follow the
        // persisted turn; do not send another generation or trust sandbox uptime.
        yield { event: "astra.recovering", data: { label: "Live stream disconnected. Following the turn’s saved progress…" } };
      } else if (backendError) {
        throw streamError ?? new Error("The backend could not start the turn.");
      } else if (++missing >= 3) {
        if (++submissionAttempts >= 3) throw new TurnConnectionError("Connection lost before submission could be confirmed. Refresh this session to check its status; no cancellation was sent.");
        // Acceptance is uncertain. The caller must reuse the exact message ID,
        // text and attachments so the backend's idempotency guard is preserved.
        break;
      }
      await wait(3000, signal);
    }
  }
  signal.throwIfAborted();
}

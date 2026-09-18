import { getToken } from "@/lib/session";

export interface TaskStreamEvent {
  type: "progress" | "assistant_delta" | "assistant_final" | string;
  task_id?: number;
  status?: string;
  progress?: number;
  processed_count?: number;
  total_count?: number;
  delta?: string;
  content?: string;
}

const TERMINAL_STATUSES = new Set([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "WAITING_APPROVAL",
]);

export function isTerminalStatus(status?: string): boolean {
  return status ? TERMINAL_STATUSES.has(status) : false;
}

/**
 * Streams task events with `fetch` instead of `EventSource`, because the API
 * authenticates with an `Authorization` header that `EventSource` cannot send.
 */
export async function streamTaskEvents(
  taskId: number,
  onEvent: (event: TaskStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/user/tasks/${taskId}/events`, {
    headers: {
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error("Tidak dapat membuka aliran status task.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        for (const line of chunk.split("\n")) {
          // Keep-alive frames start with ":" and carry no payload.
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          try {
            onEvent(JSON.parse(raw) as TaskStreamEvent);
          } catch {
            // Ignore malformed frames rather than dropping the whole stream.
          }
        }

        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}

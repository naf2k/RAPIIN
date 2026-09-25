import { apiDelete, apiGet, apiPost } from "@/lib/api";
import type { Conversation, Message } from "@/lib/types";

const MAX_SESSIONS = 20;

export interface ChatSessionMeta {
  id: number;
  title: string;
  updatedAt: number;
  turnCount: number;
}

function titleFrom(messages: Message[], fallback: string): string {
  const firstPrompt = messages.find((message) => message.role === "user")?.content.trim() ?? "";
  if (!firstPrompt) return fallback;
  return firstPrompt.length > 42 ? `${firstPrompt.slice(0, 42)}…` : firstPrompt;
}

/**
 * Conversations come from the API. The server stores a placeholder title, so the
 * list derives a readable title and message count from each conversation's messages.
 */
export async function listSessions(): Promise<ChatSessionMeta[]> {
  const conversations = await apiGet<Conversation[]>("/user/conversations");
  const recent = conversations.slice(0, MAX_SESSIONS);

  const details = await Promise.all(
    recent.map(async (conversation) => {
      try {
        const messages = await apiGet<Message[]>(
          `/user/conversations/${conversation.id}/messages`,
        );
        return {
          turnCount: messages.filter((message) => message.role === "user").length,
          title: titleFrom(messages, conversation.title || "Percakapan baru"),
        };
      } catch {
        return { turnCount: 0, title: conversation.title || "Percakapan baru" };
      }
    }),
  );

  return recent.map((conversation, index) => ({
    id: conversation.id,
    title: details[index].title,
    updatedAt: Date.parse(conversation.updated_at) || Date.now(),
    turnCount: details[index].turnCount,
  }));
}

export async function createSession(): Promise<number> {
  const created = await apiPost<{ conversation_id: number; title: string }>(
    "/user/conversations",
    {},
  );
  return created.conversation_id;
}

export function loadMessages(conversationId: number): Promise<Message[]> {
  return apiGet<Message[]>(`/user/conversations/${conversationId}/messages`);
}

export function deleteConversation(conversationId: number): Promise<{ status: string }> {
  return apiDelete<{ status: string }>(`/user/conversations/${conversationId}`);
}

export function timeLabel(updatedAt: number): string {
  const diffMinutes = Math.max(0, Math.round((Date.now() - updatedAt) / 60000));
  if (diffMinutes < 1) return "Baru saja";
  if (diffMinutes < 60) return `${diffMinutes} mnt lalu`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} jam lalu`;
  return new Date(updatedAt).toLocaleDateString("id-ID", { day: "numeric", month: "short" });
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowUpIcon,
  ChevronRight,
  CopyCheck,
  FilePenLine,
  FileSearch,
  FileText,
  FolderCog,
  FolderInput,
  FolderTree,
  MonitorCheck,
  Paperclip,
} from "lucide-react";

import { ThinkingState, type TraceNode } from "@/components/ui/ai-agent-response";
import { FileListCard, parseFileListing } from "@/components/ui/rapiin-file-list";
import {
  EMPTY_APPROVAL,
  TaskFlow,
  approvalToFlow,
  countFailures,
  emptyFlow,
  isDestructiveTool,
  parseTaskResult,
  statusStep,
  taskTypeLabel,
  type TaskFlowState,
} from "@/components/ui/rapiin-task-flow";
import { Button } from "@/components/ui/button";
import { StreamingText, MarkdownInline } from "@/components/ui/streaming-text";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import { createSession } from "@/lib/chat-store";
import { isTerminalStatus, streamTaskEvents } from "@/lib/sse";
import type {
  ApplyRecommendationResponse,
  Approval,
  FileListing,
  Message,
  OrganizerRecommendation,
  SendMessageResponse,
  Task,
  TaskStatus,
  ToolEvent,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface AutoResizeProps {
  minHeight: number;
  maxHeight?: number;
}

type ChatPhase = "idle" | "moon-transition" | "active";
type TurnStatus = "working" | "answering" | "complete";

export interface ThinkingBlock {
  text: string;
  seconds: number;
}

export interface ChatTurn {
  id: string;
  prompt: string;
  answer: string;
  followUps: string[];
  status: TurnStatus;
  taskId: number | null;
  error: string | null;
  seenStatuses: TaskStatus[];
  progress: number;
  processed: number;
  total: number;
  toolEvents: ToolEvent[];
  recommendations: OrganizerRecommendation[];
  directory: string | null;
  approval: Approval | null;
  flow: TaskFlowState | null;
  /** Folder listing the tools produced, if the work involved one. */
  listing: FileListing | null;
  /** Model text streaming right now, shown live in the working indicator. */
  thinkingLive: string;
  /** Narration the model produced on earlier agent turns, before its answer. */
  thinkingBlocks: ThinkingBlock[];
  /** When the current live block started, so its duration is measured, not guessed. */
  thinkingStartedAt: number | null;
  /** Last task progress marker; a change means a new agent turn began. */
  progressMarker: number | null;
}

const quickActionPrompts: Record<string, string> = {
  "Rapikan Downloads": "Rapihin folder Downloads gue",
  "Cari Dokumen": "Cari file laporan bulan lalu",
  "Cek Duplikat": "Cek file yang duplikat",
  "Kelompokkan File": "Kelompokkan dokumen berdasarkan tipe dan tahun",
  "Pindahkan File": "Pindahkan file yang sudah aku setujui",
  "Rename File": "Rename dokumen supaya lebih rapi",
  "Pahami Dokumen": "Pahami isi dokumen ini",
  "Periksa Device": "Cek status device RAPIIN",
};

const primaryQuickActions = [
  { label: "Cari Dokumen", Icon: FileSearch },
  { label: "Cek Duplikat", Icon: CopyCheck },
  { label: "Kelompokkan File", Icon: FolderTree },
  { label: "Pindahkan File", Icon: FolderInput },
  { label: "Rename File", Icon: FilePenLine },
  { label: "Pahami Dokumen", Icon: FileText },
] as const;

const secondaryQuickActions = [
  { label: "Rapikan Downloads", Icon: FolderCog },
  { label: "Periksa Device", Icon: MonitorCheck },
] as const;

const followUpPrompts = ["Cek file yang duplikat", "Cari file laporan bulan lalu"];

const STATUS_LABELS: Partial<Record<TaskStatus, string>> = {
  PENDING: "Menyiapkan pekerjaan",
  PLANNING: "Memahami permintaan",
  RUNNING: "Mengerjakan permintaan",
  VERIFYING: "Memverifikasi hasil",
  WAITING_APPROVAL: "Menunggu persetujuan",
  COMPLETED: "Selesai",
  FAILED: "Gagal",
  CANCELLED: "Dibatalkan",
};

const EASE_OUT = [0.22, 1, 0.36, 1] as const;

function useAutoResizeTextarea({ minHeight, maxHeight }: AutoResizeProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`;
      const newHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Infinity),
      );
      textarea.style.height = `${newHeight}px`;
    },
    [minHeight, maxHeight],
  );

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = `${minHeight}px`;
    }
  }, [minHeight]);

  return { textareaRef, adjustHeight };
}

function messageOf(cause: unknown, fallback: string): string {
  return cause instanceof ApiError ? cause.message : fallback;
}

function delay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

function addStatus(seen: TaskStatus[], status?: string): TaskStatus[] {
  if (!status || !(status in STATUS_LABELS)) return seen;
  const next = status as TaskStatus;
  return seen.includes(next) ? seen : [...seen, next];
}

function makeTurn(id: string, prompt: string): ChatTurn {
  return {
    id,
    prompt,
    answer: "",
    followUps: followUpPrompts,
    status: "working",
    taskId: null,
    error: null,
    seenStatuses: [],
    progress: 0,
    processed: 0,
    total: 0,
    toolEvents: [],
    recommendations: [],
    directory: null,
    approval: null,
    flow: null,
    listing: null,
    thinkingLive: "",
    thinkingBlocks: [],
    thinkingStartedAt: null,
    progressMarker: null,
  };
}

/** Moves the text the model has finished emitting out of the live slot. */
function archiveThinking(
  turn: ChatTurn,
  text: string,
  startedAt: number | null,
): Partial<ChatTurn> {
  const trimmed = text.trim();
  if (!trimmed) return { thinkingLive: "", thinkingStartedAt: null };
  const seconds = startedAt
    ? Math.max(1, Math.round((Date.now() - startedAt) / 1000))
    : 1;
  return {
    thinkingLive: "",
    thinkingStartedAt: null,
    thinkingBlocks: [...turn.thinkingBlocks, { text: trimmed, seconds }],
  };
}

/** Splits model narration into readable rows for the expandable trace. */
function narrationSentences(text: string): string[] {
  return text
    .split(/\n+/)
    .flatMap((line) => line.split(/(?<=[.!?])\s+/))
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .slice(0, 12);
}

/**
 * The indicator is a single line by design, so it shows the newest line the
 * model wrote; the full narration stays in the expandable trace.
 */
function liveIndicatorLabel(turn: ChatTurn): string {
  const lines = turn.thinkingLive.split("\n").filter((line) => line.trim());
  const last = lines.length > 0 ? lines[lines.length - 1].trim() : "";
  if (!last) return "RAPIIN sedang bekerja...";
  return last.length > 140 ? `${last.slice(0, 140)}…` : last;
}

function turnsFromMessages(messages: Message[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let current: ChatTurn | null = null;

  for (const message of messages) {
    if (message.role === "user") {
      current = makeTurn(`history-${message.id}`, message.content);
      current.status = "complete";
      turns.push(current);
    } else if (message.role === "assistant") {
      if (!current) continue;
      current.answer = current.answer
        ? `${current.answer}\n\n${message.content}`
        : message.content;
    }
  }

  return turns.filter((turn) => turn.prompt.trim() || turn.answer.trim());
}

function traceNodesFor(turn: ChatTurn): TraceNode[] {
  const nodes: TraceNode[] = [];

  // What the model actually wrote while it worked, turn by turn.
  turn.thinkingBlocks.forEach((block, index) => {
    nodes.push({
      id: `thinking-${index}`,
      type: "reasoning",
      sentences: narrationSentences(block.text),
      durationSeconds: block.seconds,
    });
  });

  for (const status of turn.seenStatuses) {
    if (status === "FAILED" || status === "CANCELLED") continue;
    nodes.push({
      id: `status-${status}`,
      type: "step",
      primary: STATUS_LABELS[status] ?? status,
      secondary:
        status === "RUNNING" && turn.total > 0
          ? `${turn.processed} / ${turn.total}`
          : undefined,
      status: status === "COMPLETED" ? "completed" : undefined,
    });
  }

  if (turn.error) {
    nodes.push({
      id: "turn-error",
      type: "step",
      primary: "Gagal",
      secondary: turn.error,
      status: "failed",
    });
  }

  return nodes;
}

function toFlowRecommendation(recommendation: OrganizerRecommendation) {
  return {
    title: recommendation.title ?? "Terapkan rekomendasi",
    detail: recommendation.detail ?? `${recommendation.count ?? 0} file`,
    count: recommendation.count ?? 0,
  };
}

function folderName(directory: string | null): string | null {
  if (!directory) return null;
  const parts = directory.split(/[\\/]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : directory;
}

/**
 * The model usually opens with one short line. Showing that above a folder card
 * reads better than burying it under the list.
 */
function splitLead(answer: string): { lead: string; rest: string } {
  const trimmed = answer.trim();
  if (!trimmed) return { lead: "", rest: "" };
  const newline = trimmed.indexOf("\n");
  if (newline === -1) return { lead: "", rest: trimmed };
  const firstLine = trimmed.slice(0, newline).trim();
  const rest = trimmed.slice(newline + 1).trim();
  if (!rest || !firstLine || firstLine.length > 200) return { lead: "", rest: trimmed };
  return { lead: firstLine, rest };
}

function taskLabelFor(task: Task | null, directory: string | null): string {
  const folder = folderName(directory);
  if (folder) return `Merapikan ${folder}`;
  return taskTypeLabel(task?.type ?? "conversation");
}

/** Tools that actually change files; a read-only scan must not show as work done. */
const MUTATING_TOOLS = new Set([
  "file_move",
  "file_copy",
  "file_rename",
  "file_delete",
  "bulk_delete",
  "batch_executor",
]);

function didMutate(toolEvents: ToolEvent[]): boolean {
  return toolEvents.some((event) => MUTATING_TOOLS.has(event.tool));
}

function buildFlow(input: {
  taskName: string;
  taskStatus: TaskStatus | null;
  total: number;
  processed: number;
  toolEvents: ToolEvent[];
  recommendations: OrganizerRecommendation[];
  approval: Approval | null;
}): TaskFlowState | null {
  const { taskName, taskStatus, total, processed, toolEvents, recommendations, approval } = input;

  if (approval) {
    const base = emptyFlow(taskName, "approval");
    return {
      ...base,
      approval: approvalToFlow(approval),
      total,
      processed,
    };
  }

  if (recommendations.length > 0) {
    const base = emptyFlow(taskName, "recommendation");
    return {
      ...base,
      recommendations: recommendations.map(toFlowRecommendation),
      total,
      processed,
    };
  }

  // Only work that changes files earns a progress or result card.
  if (total > 0 && didMutate(toolEvents)) {
    const base = emptyFlow(taskName, taskStatus === "COMPLETED" ? "result" : "progress");
    if (taskStatus === "COMPLETED") {
      const failed = countFailures(toolEvents);
      const verified = Math.max(0, processed - failed);
      return {
        ...base,
        total,
        processed,
        result: {
          summary:
            failed > 0
              ? `Selesai dengan ${failed} kendala. ${processed} dari ${total} file terproses.`
              : `Selesai. ${processed} dari ${total} file terproses dan terverifikasi.`,
          planned: total,
          executed: processed,
          verified,
          failed,
        },
      };
    }
    if (taskStatus === "FAILED" || taskStatus === "CANCELLED") return null;
    return { ...base, total, processed, steps: [statusStep(taskStatus ?? "RUNNING")] };
  }

  return null;
}

interface RuixenMoonChatProps {
  conversationId?: number | null;
  initialMessages?: Message[];
  onConversationChange?: (conversationId: number) => void;
  onTurnSettled?: () => void;
}

export default function RuixenMoonChat({
  conversationId = null,
  initialMessages,
  onConversationChange,
  onTurnSettled,
}: RuixenMoonChatProps) {
  const [message, setMessage] = useState("");
  const restoredTurns = turnsFromMessages(initialMessages ?? []);
  const [phase, setPhase] = useState<ChatPhase>(restoredTurns.length > 0 ? "active" : "idle");
  const [hasShownMoon, setHasShownMoon] = useState(restoredTurns.length > 0);
  const [turns, setTurns] = useState<ChatTurn[]>(restoredTurns);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(
    restoredTurns.length > 0 ? restoredTurns[restoredTurns.length - 1].id : null,
  );
  const runIdRef = useRef(restoredTurns.length);
  const conversationIdRef = useRef<number | null>(conversationId);
  const turnsRef = useRef<ChatTurn[]>(restoredTurns);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 48,
    maxHeight: 150,
  });
  const reducedMotion = useReducedMotion();

  const activeTurn = turns.find((turn) => turn.id === activeTurnId);
  const isBusy = activeTurn?.status === "working" || activeTurn?.status === "answering";
  const shouldHideLanding = phase === "moon-transition";
  const lastTurnId = turns.length > 0 ? turns[turns.length - 1].id : null;

  const updateTurn = useCallback(
    (turnId: string, patch: Partial<ChatTurn> | ((turn: ChatTurn) => Partial<ChatTurn>)) => {
      setTurns((currentTurns) =>
        currentTurns.map((turn) => {
          if (turn.id !== turnId) return turn;
          const next = typeof patch === "function" ? patch(turn) : patch;
          return { ...turn, ...next };
        }),
      );
    },
    [],
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: reducedMotion ? "auto" : "smooth",
      block: "nearest",
    });
  }, [reducedMotion, phase, turns]);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  const watchTask = useCallback(
    async (turnId: string, taskId: number, signal?: AbortSignal) => {
      try {
        await streamTaskEvents(
          taskId,
          (event) => {
            if (event.type === "assistant_delta" && event.delta) {
              // The model's own text. It stays live in the working indicator
              // until we know whether this turn produced the final answer.
              updateTurn(turnId, (turn) => ({
                ...turn,
                thinkingLive: turn.thinkingLive + event.delta,
                thinkingStartedAt: turn.thinkingStartedAt ?? Date.now(),
              }));
              return;
            }
            if (event.type === "assistant_final") {
              const finalContent = event.content ?? "";
              updateTurn(turnId, (turn) => {
                // The answer repeats at the tail of the stream, so everything
                // before it is narration the model produced while working.
                const narration =
                  finalContent && turn.thinkingLive.endsWith(finalContent)
                    ? turn.thinkingLive.slice(0, -finalContent.length)
                    : turn.thinkingLive;
                return {
                  ...turn,
                  ...archiveThinking(turn, narration, turn.thinkingStartedAt),
                  answer: finalContent || turn.answer,
                  // The stream and the poll run concurrently, so a late
                  // assistant_final must never undo a finished turn.
                  status: turn.status === "complete" ? "complete" : "answering",
                };
              });
              return;
            }
            if (event.type === "progress") {
              updateTurn(turnId, (turn) => {
                const nextProgress = event.progress ?? turn.progress;
                const beganNewTurn =
                  turn.progressMarker !== null && nextProgress !== turn.progressMarker;
                return {
                  ...turn,
                  // A progress bump means the agent finished a turn and moved
                  // on, so whatever it wrote belongs to the trace.
                  ...(beganNewTurn
                    ? archiveThinking(turn, turn.thinkingLive, turn.thinkingStartedAt)
                    : {}),
                  progressMarker: nextProgress,
                  progress: event.progress ?? turn.progress,
                  processed: event.processed_count ?? turn.processed,
                  total: event.total_count ?? turn.total,
                  seenStatuses: addStatus(turn.seenStatuses, event.status),
                };
              });
            }
          },
          signal,
        );
      } catch {
        // A dropped stream is not a failed task; task state is fetched below.
      }
    },
    [updateTurn],
  );

  const pollTask = useCallback(
    async (turnId: string, taskId: number, signal?: AbortSignal): Promise<Task | null> => {
      // The queue worker runs in its own process, so the in-memory event stream
      // cannot be the source of truth. Polling always is.
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await delay(1500, signal);
        if (signal?.aborted) return null;

        let task: Task;
        try {
          task = await apiGet<Task>(`/user/tasks/${taskId}`);
        } catch {
          return null;
        }

        updateTurn(turnId, (turn) => ({
          ...turn,
          progress: task.progress ?? turn.progress,
          processed: task.processed_count ?? turn.processed,
          total: task.total_count ?? turn.total,
          seenStatuses: addStatus(turn.seenStatuses, task.status),
        }));

        if (isTerminalStatus(task.status)) return task;
      }
      return null;
    },
    [updateTurn],
  );

  const finalizeTurn = useCallback(
    async (turnId: string, taskId: number, task: Task | null, targetConversationId: number | null) => {
      const resolvedTask =
        task ?? (await apiGet<Task>(`/user/tasks/${taskId}`).catch(() => null));

      let approval: Approval | null = null;
      try {
        const approvals = await apiGet<Approval[]>("/user/approvals");
        approval = approvals.find((item) => item.task_id === taskId) ?? null;
      } catch {
        approval = null;
      }

      // Without a live stream the answer only exists in the conversation.
      let answer: string | null = null;
      const existing = turnsRef.current.find((item) => item.id === turnId);
      if (targetConversationId !== null && !existing?.answer.trim()) {
        try {
          const messages = await apiGet<Message[]>(
            `/user/conversations/${targetConversationId}/messages`,
          );
          const lastAssistant = [...messages]
            .reverse()
            .find((message) => message.role === "assistant");
          answer = lastAssistant?.content ?? null;
        } catch {
          answer = null;
        }
      }

      const parsed = resolvedTask
        ? parseTaskResult(resolvedTask)
        : { toolEvents: [], recommendations: [], directory: null, toolResult: null };

      updateTurn(turnId, (turn) => {
        const total = resolvedTask?.total_count || turn.flow?.total || turn.total;
        const processed = resolvedTask?.processed_count ?? turn.processed;
        const nextApproval = approval ?? turn.approval;
        const merged: ChatTurn = {
          ...turn,
          // Anything the model wrote and never handed over as a final answer
          // still belongs in the trace rather than being dropped.
          ...archiveThinking(turn, turn.thinkingLive, turn.thinkingStartedAt),
          status: "complete",
          answer: answer ?? turn.answer,
          progress: resolvedTask?.progress ?? turn.progress,
          processed,
          total,
          error: resolvedTask?.error ?? null,
          toolEvents: parsed.toolEvents,
          recommendations: parsed.recommendations,
          directory: parsed.directory,
          approval: nextApproval,
          listing: parseFileListing(parsed.toolEvents, parsed.toolResult),
          seenStatuses: resolvedTask
            ? addStatus(turn.seenStatuses, resolvedTask.status)
            : turn.seenStatuses,
        };

        // A cancelled flow stays cancelled; nothing should reopen it.
        if (turn.flow?.stage === "cancelled") return { ...merged, flow: turn.flow };

        return {
          ...merged,
          flow: buildFlow({
            taskName: taskLabelFor(resolvedTask, parsed.directory),
            taskStatus: resolvedTask?.status ?? null,
            total,
            processed,
            toolEvents: parsed.toolEvents,
            recommendations: parsed.recommendations,
            approval: nextApproval,
          }),
        };
      });

      onTurnSettled?.();
    },
    [onTurnSettled, updateTurn],
  );

  const trackTask = useCallback(
    async (
      turnId: string,
      taskId: number,
      targetConversationId: number | null,
      signal?: AbortSignal,
    ) => {
      // Live deltas are best-effort; polling decides when the task is done.
      void watchTask(turnId, taskId, signal);
      const task = await pollTask(turnId, taskId, signal);
      await finalizeTurn(turnId, taskId, task, targetConversationId);
    },
    [finalizeTurn, pollTask, watchTask],
  );

  const runTurn = useCallback(
    async (turnId: string, prompt: string, targetConversationId: number, signal?: AbortSignal) => {
      let sent: SendMessageResponse;
      try {
        sent = await apiPost<SendMessageResponse>(
          `/user/conversations/${targetConversationId}/messages`,
          { content: prompt },
        );
      } catch (cause) {
        updateTurn(turnId, {
          status: "complete",
          error: messageOf(cause, "RAPIIN belum bisa memproses permintaan ini."),
        });
        onTurnSettled?.();
        return;
      }

      updateTurn(turnId, { taskId: sent.task_id });
      await trackTask(turnId, sent.task_id, targetConversationId, signal);
    },
    [onTurnSettled, trackTask, updateTurn],
  );

  const startTurn = useCallback(
    (rawPrompt: string) => {
      const prompt = rawPrompt.trim();
      if (!prompt || isBusy) return false;

      runIdRef.current += 1;
      const turnId = `turn-${runIdRef.current}`;

      setTurns((currentTurns) => [...currentTurns, makeTurn(turnId, prompt)]);
      setActiveTurnId(turnId);

      if (!hasShownMoon && !reducedMotion) {
        setPhase("moon-transition");
      } else {
        setHasShownMoon(true);
        setPhase("active");
      }

      void (async () => {
        let targetConversationId = conversationIdRef.current;
        if (targetConversationId === null) {
          try {
            targetConversationId = await createSession();
            conversationIdRef.current = targetConversationId;
            onConversationChange?.(targetConversationId);
          } catch (cause) {
            updateTurn(turnId, {
              status: "complete",
              error: messageOf(cause, "Tidak dapat memulai percakapan baru."),
            });
            return;
          }
        }
        await runTurn(turnId, prompt, targetConversationId);
      })();

      return true;
    },
    [
      hasShownMoon,
      isBusy,
      onConversationChange,
      reducedMotion,
      runTurn,
      updateTurn,
    ],
  );

  const handleApply = useCallback(
    (turnId: string, index: number) => {
      const turn = turns.find((item) => item.id === turnId);
      if (!turn?.taskId) return;
      const recommendation = turn.recommendations[index];
      if (!recommendation) return;

      apiPost<ApplyRecommendationResponse>("/user/recommendations/apply", {
        source_task_id: turn.taskId,
        recommendation_id: recommendation.id,
      })
        .then(async (applied) => {
          let approval: Approval | null = null;
          try {
            const approvals = await apiGet<Approval[]>("/user/approvals");
            approval = approvals.find((item) => item.id === applied.approval_id) ?? null;
          } catch {
            approval = null;
          }

          updateTurn(turnId, (current) => ({
            ...current,
            approval,
            flow: current.flow
              ? {
                  ...current.flow,
                  stage: "approval",
                  selected: index,
                  total: applied.file_count,
                  processed: 0,
                  approval: approval
                    ? approvalToFlow(approval)
                    : {
                        ...EMPTY_APPROVAL,
                        action: applied.action,
                        scope: current.directory ?? "—",
                        destructive: isDestructiveTool(applied.tool),
                      },
                }
              : null,
          }));
        })
        .catch((cause: unknown) => {
          updateTurn(turnId, {
            error: messageOf(cause, "Rekomendasi tidak dapat diterapkan."),
          });
        });
    },
    [turns, updateTurn],
  );

  const handleDecide = useCallback(
    (turnId: string, decision: "APPROVED" | "REJECTED") => {
      const turn = turns.find((item) => item.id === turnId);
      if (!turn?.approval) return;
      const { approval } = turn;

      apiPost<Approval>(`/user/approvals/${approval.id}/respond`, { decision })
        .then(() => {
          if (decision === "REJECTED") {
            updateTurn(turnId, (current) => ({
              ...current,
              approval: null,
              flow: current.flow ? { ...current.flow, stage: "cancelled", approval: { ...current.flow.approval, reviewing: false } } : null,
            }));
            onTurnSettled?.();
            return;
          }

          // The engine hands the stored action to the device agent, so the task
          // keeps running after the decision.
          updateTurn(turnId, (current) => ({
            ...current,
            approval: null,
            status: "working",
            progress: 0,
            processed: 0,
            error: null,
            flow: current.flow
              ? { ...current.flow, stage: "progress", approval: { ...current.flow.approval, reviewing: false } }
              : null,
          }));
          setActiveTurnId(turnId);
          const approvalTaskId = approval.task_id;
          if (approvalTaskId) {
            void trackTask(turnId, approvalTaskId, conversationIdRef.current);
          }
        })
        .catch((cause: unknown) => {
          updateTurn(turnId, {
            error: messageOf(cause, "Keputusan tidak dapat dikirim."),
          });
        });
    },
    [onTurnSettled, trackTask, turns, updateTurn],
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!startTurn(message)) return;

    setMessage("");
    adjustHeight(true);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const handleMoonComplete = () => {
    if (phase !== "moon-transition") return;
    setHasShownMoon(true);
    setPhase("active");
  };

  const updateFlow = (turnId: string, next: TaskFlowState) => {
    updateTurn(turnId, { flow: next });
  };

  const handleQuickAction = (label: string) => {
    if (isBusy || phase === "moon-transition") return;
    setMessage(quickActionPrompts[label] ?? label);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const renderComposer = (compact = false) => (
    <motion.div
      initial={
        compact || reducedMotion
          ? false
          : {
              opacity: 0,
              transform: "translate3d(0, 14px, 0) scale(0.99)",
            }
      }
      animate={{ opacity: 1, transform: "translate3d(0, 0, 0) scale(1)" }}
      transition={{ duration: 0.56, delay: compact ? 0 : 0.5, ease: EASE_OUT }}
      className={cn("mx-auto w-full max-w-3xl", compact ? "px-4 pb-6 sm:px-0" : "px-4 sm:px-0")}
    >
      <form
        onSubmit={handleSubmit}
        className="relative rounded-xl border border-neutral-700 bg-black/70 backdrop-blur-md"
      >
        <Textarea
          ref={textareaRef}
          value={message}
          disabled={isBusy || phase === "moon-transition"}
          onChange={(event) => {
            setMessage(event.target.value);
            adjustHeight();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Minta RAPIIN mengerjakan sesuatu..."
          aria-label="Pesan untuk RAPIIN"
          className={cn(
            "w-full resize-none border-none px-4 py-3",
            "bg-transparent text-sm text-white",
            "focus-visible:ring-0 focus-visible:ring-offset-0",
            "min-h-[48px] placeholder:text-neutral-400",
          )}
          style={{ overflow: "hidden" }}
        />

        <div className="flex items-center justify-between p-3">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled={isBusy || phase === "moon-transition"}
            className="text-white hover:bg-neutral-700"
            aria-label="Lampirkan file"
          >
            <Paperclip className="h-4 w-4" />
          </Button>

          <Button
            type="submit"
            disabled={!message.trim() || isBusy || phase === "moon-transition"}
            aria-label="Kirim pesan"
            className={cn(
              "flex items-center gap-1 rounded-lg px-3 py-2 transition-colors",
              message.trim() && !isBusy && phase !== "moon-transition"
                ? "bg-white text-black hover:bg-neutral-200"
                : "cursor-not-allowed bg-neutral-700 text-neutral-400",
            )}
          >
            <ArrowUpIcon className="h-4 w-4" />
            <span className="sr-only">Kirim</span>
          </Button>
        </div>
      </form>
    </motion.div>
  );

  const renderQuickActions = () => (
    <motion.div
      initial={
        reducedMotion
          ? false
          : { opacity: 0, transform: "translate3d(0, 10px, 0)" }
      }
      animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
      transition={{ duration: 0.52, delay: 0.68, ease: EASE_OUT }}
      className="mx-auto mt-6 flex w-full max-w-5xl flex-col items-center gap-3 px-4"
    >
      <div className="flex flex-wrap items-center justify-center gap-3">
        {primaryQuickActions.map(({ label, Icon }) => (
          <QuickAction
            key={label}
            icon={<Icon className="h-4 w-4" strokeWidth={1.8} />}
            label={label}
            onClick={handleQuickAction}
            disabled={isBusy || phase === "moon-transition"}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        {secondaryQuickActions.map(({ label, Icon }) => (
          <QuickAction
            key={label}
            icon={<Icon className="h-4 w-4" strokeWidth={1.8} />}
            label={label}
            onClick={handleQuickAction}
            disabled={isBusy || phase === "moon-transition"}
          />
        ))}
      </div>
    </motion.div>
  );

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#050505]">
      <AnimatePresence>
        {!hasShownMoon && (
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
            style={{ transformOrigin: "50% 100%" }}
            initial={
              reducedMotion
                ? false
                : {
                    opacity: 0.35,
                    transform: "translate3d(0, 24%, 0) scale(0.97)",
                  }
            }
            animate={
              shouldHideLanding
                ? {
                    opacity: 0.9,
                    transform: "translate3d(0, -110%, 0) scale(1.02)",
                  }
                : { opacity: 1, transform: "translate3d(0, 0, 0) scale(1)" }
            }
            transition={
              reducedMotion
                ? { duration: 0 }
                : shouldHideLanding
                  ? { duration: 1.35, ease: EASE_OUT }
                  : { duration: 1.28, ease: EASE_OUT }
            }
            onAnimationComplete={handleMoonComplete}
          >
            <motion.div
              className="absolute -inset-[2%] bg-cover bg-center"
              style={{
                backgroundColor: "#050505",
                backgroundImage:
                  "url('https://cdn.21st.dev/assets/mirror/c3/c333918af688a4a8a3d004652e6c0ee219457a9d84d380eeb31f513d4b59a09f.png')",
                transformOrigin: "50% 82%",
              }}
              animate={
                reducedMotion || shouldHideLanding
                  ? { transform: "translate3d(0, 0, 0) scale(1)" }
                  : {
                      transform: [
                        "translate3d(0, 0, 0) scale(1)",
                        "translate3d(0, -0.9%, 0) scale(1.007)",
                        "translate3d(0, 0.35%, 0) scale(1.002)",
                        "translate3d(0, 0, 0) scale(1)",
                      ],
                    }
              }
              transition={
                reducedMotion || shouldHideLanding
                  ? { duration: 0 }
                  : {
                      duration: 9,
                      delay: 1.25,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }
              }
            />
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        className="relative z-10 flex h-full min-h-0 w-full flex-col"
        animate={
          shouldHideLanding
            ? { opacity: 0, transform: "translate3d(0, -18px, 0)" }
            : { opacity: 1, transform: "translate3d(0, 0, 0)" }
        }
        transition={
          reducedMotion
            ? { duration: 0 }
            : {
                duration: 0.72,
                delay: shouldHideLanding ? 0.12 : 0,
                ease: EASE_OUT,
              }
        }
      >
        {!hasShownMoon ? (
          <>
            <div className="flex w-full flex-1 flex-col items-center justify-center px-4">
              <motion.div
                initial={
                  reducedMotion
                    ? false
                    : { opacity: 0, transform: "translate3d(0, 10px, 0)" }
                }
                animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
                transition={{ duration: 0.56, delay: 0.3, ease: EASE_OUT }}
                className="text-center"
              >
                <h1 className="text-4xl font-semibold text-white drop-shadow-sm">
                  RAPIIN
                </h1>
                <p className="mt-2 text-neutral-200">
                  Bilang apa yang ingin dikerjakan. RAPIIN yang mengerjakan.
                </p>
              </motion.div>
            </div>
            <div className="mb-[12vh] w-full px-4 sm:mb-[20vh] sm:px-0">
              {renderComposer()}
              {renderQuickActions()}
            </div>
          </>
        ) : (
          <>
            <div
              className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:py-12"
              aria-busy={isBusy}
              aria-label="Percakapan RAPIIN"
            >
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
                {turns.map((turn) => {
                  const isActiveTurn = turn.id === activeTurnId;
                  const showWorkflow = isActiveTurn && turn.status === "working";
                  const showStreamingAnswer = isActiveTurn && turn.status === "answering";
                  const showCompletedAnswer = turn.status === "complete";

                  return (
                    <div key={turn.id} className="flex flex-col gap-4">
                      <div className="flex justify-end">
                        <div className="max-w-[88%] rounded-2xl rounded-br-md bg-white px-4 py-3 text-sm leading-relaxed text-neutral-900 shadow-sm">
                          {turn.prompt}
                        </div>
                      </div>

                      {(showWorkflow || showStreamingAnswer || showCompletedAnswer) && (
                        <div className="w-full pl-1 sm:pl-4">
                          {showWorkflow && (
                            <ThinkingState
                              key={`workflow-${turn.id}`}
                              nodes={traceNodesFor(turn)}
                              running
                              autoPlay={false}
                              defaultExpanded={false}
                              workingLabel={liveIndicatorLabel(turn)}
                              reducedMotion={Boolean(reducedMotion)}
                            />
                          )}

                          {(() => {
                            const hasCard = showCompletedAnswer && Boolean(turn.listing);
                            const { lead, rest } = hasCard
                              ? splitLead(turn.answer)
                              : { lead: "", rest: turn.answer };

                            return (
                              <>
                                {hasCard && lead && (
                                  <p className="mb-3 text-[13.5px] leading-relaxed text-neutral-200">
                                    <MarkdownInline text={lead} />
                                  </p>
                                )}

                                {hasCard && turn.listing && (
                                  <div className={cn("mb-3", !rest && "mb-0")}>
                                    <FileListCard listing={turn.listing} />
                                  </div>
                                )}

                                {(showStreamingAnswer || showCompletedAnswer) && (
                                  <StreamingText
                                    key={`answer-${turn.id}`}
                                    text={rest}
                                    sources={[]}
                                    followUps={turn.followUps}
                                    isStreaming={showStreamingAnswer}
                                    mode="live"
                                    format="markdown"
                                    onFollowUp={startTurn}
                                    onRetry={() => startTurn(turn.prompt)}
                                  />
                                )}
                              </>
                            );
                          })()}

                          {turn.error && showCompletedAnswer && (
                            <p role="alert" className="mt-2 text-[13px] leading-relaxed text-red-300">
                              {turn.error}
                            </p>
                          )}

                          {showCompletedAnswer && turn.flow && (
                            <div className="mt-4">
                              <TaskFlow
                                key={`flow-${turn.id}`}
                                flow={turn.flow}
                                interactive={turn.id === lastTurnId}
                                reducedMotion={Boolean(reducedMotion)}
                                onTransition={(next) => updateFlow(turn.id, next)}
                                onApply={(index) => handleApply(turn.id, index)}
                                onDecide={(decision) => handleDecide(turn.id, decision)}
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>
            </div>
            {renderComposer(true)}
          </>
        )}
      </motion.div>
    </div>
  );
}

interface QuickActionProps {
  icon: ReactNode;
  label: string;
  onClick: (label: string) => void;
  disabled?: boolean;
}

function QuickAction({ icon, label, onClick, disabled = false }: QuickActionProps) {
  return (
    <Button
      type="button"
      variant="outline"
      disabled={disabled}
      onClick={() => onClick(label)}
      className="flex items-center gap-2 rounded-full border-neutral-700 bg-black/50 text-neutral-300 hover:bg-neutral-700 hover:text-white"
    >
      {icon}
      <span className="text-xs">{label}</span>
    </Button>
  );
}

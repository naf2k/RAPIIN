"use client";

import {
  CheckCircle2,
  ChevronRight,
  FileCheck2,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { Approval, OrganizerRecommendation, Task, ToolEvent } from "@/lib/types";

export interface FlowRecommendation {
  title: string;
  detail: string;
  count: number;
}

export type FlowStage = "recommendation" | "approval" | "progress" | "result" | "cancelled";

export interface TaskFlowState {
  taskName: string;
  stage: FlowStage;
  recommendations: FlowRecommendation[];
  selected: number | null;
  approval: {
    action: string;
    consequence: string;
    scope: string;
    risk: string;
    destructive: boolean;
    reviewing: boolean;
    /** Policy puts this decision in a supervisor's hands, not the user's. */
    requiresSupervisor: boolean;
  };
  total: number;
  processed: number;
  steps: string[];
  result: {
    summary: string;
    planned: number;
    executed: number;
    verified: number;
    failed: number;
  } | null;
}

export const EMPTY_APPROVAL: TaskFlowState["approval"] = {
  action: "",
  consequence: "",
  scope: "",
  risk: "",
  destructive: false,
  reviewing: false,
  requiresSupervisor: false,
};

const DESTRUCTIVE_TOOLS = new Set(["file_delete", "bulk_delete", "batch_delete"]);

const TASK_TYPE_LABELS: Record<string, string> = {
  conversation: "Percakapan",
  organize: "Merapikan file",
};

const STATUS_STEPS: Record<string, string> = {
  PENDING: "Menyiapkan pekerjaan…",
  PLANNING: "Menyusun rencana…",
  RUNNING: "Menjalankan pekerjaan…",
  VERIFYING: "Memverifikasi hasil…",
  WAITING_APPROVAL: "Menunggu persetujuan Anda…",
};

export function taskTypeLabel(type: string): string {
  return TASK_TYPE_LABELS[type] ?? "Mengerjakan permintaan";
}

export function statusStep(status: string): string {
  return STATUS_STEPS[status] ?? "Mengerjakan permintaan…";
}

export function emptyFlow(taskName: string, stage: FlowStage = "progress"): TaskFlowState {
  return {
    taskName,
    stage,
    recommendations: [],
    selected: null,
    approval: { ...EMPTY_APPROVAL },
    total: 0,
    processed: 0,
    steps: [],
    result: null,
  };
}

export function parseTaskResult(task: Pick<Task, "result_json">): {
  toolEvents: ToolEvent[];
  recommendations: OrganizerRecommendation[];
  directory: string | null;
  toolResult: unknown;
} {
  const toolEvents: ToolEvent[] = [];
  const recommendations: OrganizerRecommendation[] = [];
  let directory: string | null = null;
  let toolResult: unknown = null;

  if (!task.result_json) return { toolEvents, recommendations, directory, toolResult };

  let parsed: unknown;
  try {
    parsed = JSON.parse(task.result_json);
  } catch {
    return { toolEvents, recommendations, directory, toolResult };
  }
  if (!parsed || typeof parsed !== "object") {
    return { toolEvents, recommendations, directory, toolResult };
  }

  const result = parsed as { tool_events?: ToolEvent[]; tool_result?: unknown };
  if (Array.isArray(result.tool_events)) toolEvents.push(...result.tool_events);
  if (result.tool_result) toolResult = result.tool_result;

  const candidates: unknown[] = [];
  if (result.tool_result) candidates.push(result.tool_result);
  for (const event of toolEvents) {
    if (event.tool === "folder_organizer" && event.result) candidates.push(event.result);
  }

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    const organizer = candidate as { directory?: string; recommendations?: OrganizerRecommendation[] };
    if (typeof organizer.directory === "string") directory = organizer.directory;
    if (Array.isArray(organizer.recommendations)) recommendations.push(...organizer.recommendations);
  }

  return { toolEvents, recommendations, directory, toolResult };
}

export function isDestructiveTool(toolName?: string | null): boolean {
  return toolName ? DESTRUCTIVE_TOOLS.has(toolName) : false;
}

function consequenceFor(toolName: string | null): string {
  return isDestructiveTool(toolName)
    ? "File akan dihapus permanen dan tindakan ini tidak bisa dibatalkan."
    : "File diproses sesuai rencana. Tidak ada file yang dihapus.";
}

export function approvalToFlow(approval: Approval): TaskFlowState["approval"] {
  return {
    action: approval.action,
    consequence: consequenceFor(approval.tool_name),
    scope: approval.scope ?? "—",
    risk: approval.risk ?? "—",
    destructive: isDestructiveTool(approval.tool_name),
    reviewing: false,
    requiresSupervisor: approval.kind === "SUPERVISOR",
  };
}

export function countFailures(toolEvents: ToolEvent[]): number {
  return toolEvents.filter((event) => event.status === "ERROR" || event.status === "BLOCKED").length;
}

interface TaskFlowProps {
  flow: TaskFlowState;
  interactive: boolean;
  reducedMotion: boolean;
  onTransition: (next: TaskFlowState) => void;
  onApply?: (index: number) => void;
  onDecide?: (decision: "APPROVED" | "REJECTED") => void;
}

export function TaskFlow({ flow, interactive, onTransition, onApply, onDecide }: TaskFlowProps) {
  if (flow.stage === "recommendation") {
    return (
      <RecommendationView
        flow={flow}
        interactive={interactive}
        onTransition={onTransition}
        onApply={onApply}
      />
    );
  }
  if (flow.stage === "approval") {
    return <ApprovalView flow={flow} interactive={interactive} onTransition={onTransition} onDecide={onDecide} />;
  }
  if (flow.stage === "progress") {
    return <ProgressView flow={flow} />;
  }
  if (flow.stage === "result" && flow.result) {
    return <ResultView flow={flow} result={flow.result} />;
  }
  return (
    <div className="w-full max-w-[38rem]">
      <p className="flex items-center gap-2 text-[13px] text-neutral-500">
        <X className="h-3.5 w-3.5" aria-hidden="true" />
        Dibatalkan. Tidak ada file yang diubah.
      </p>
    </div>
  );
}

function RecommendationView({
  flow,
  interactive,
  onTransition,
  onApply,
}: {
  flow: TaskFlowState;
  interactive: boolean;
  onTransition: (next: TaskFlowState) => void;
  onApply?: (index: number) => void;
}) {
  return (
    <div className="w-full max-w-[38rem] rounded-xl border border-neutral-800 bg-neutral-900/50 p-5">
      <p className="text-[13.5px] leading-relaxed text-neutral-200">
        Aku menemukan <span className="font-medium text-neutral-100">{flow.recommendations.reduce((sum, item) => sum + item.count, 0)} file</span>. Aku merekomendasikan:
      </p>
      <ol className="mt-4 space-y-3">
        {flow.recommendations.map((item, index) => (
          <li key={item.title} className="flex items-start gap-3">
            <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-neutral-800 text-[11px] font-medium text-neutral-300">
              {index + 1}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-neutral-100">{item.title}</span>
              <span className="mt-0.5 block text-xs text-neutral-500">{item.detail}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-[13px] text-neutral-400">Mana yang mau diterapkan?</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {flow.recommendations.map((item, index) => (
          <button
            key={item.title}
            type="button"
            disabled={!interactive}
            onClick={() => {
              if (onApply) onApply(index);
              else onTransition({ ...flow, stage: "approval", selected: index });
            }}
            className="h-9 rounded-lg bg-neutral-100 px-3 text-[13px] font-medium text-neutral-950 transition-[background-color,transform] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 disabled:cursor-default disabled:opacity-60 active:scale-[0.98]"
          >
            Apply {index + 1}
          </button>
        ))}
      </div>
    </div>
  );
}

function ApprovalView({
  flow,
  interactive,
  onTransition,
  onDecide,
}: {
  flow: TaskFlowState;
  interactive: boolean;
  onTransition: (next: TaskFlowState) => void;
  onDecide?: (decision: "APPROVED" | "REJECTED") => void;
}) {
  const { approval } = flow;
  const destructive = approval.destructive;
  const supervisor = approval.requiresSupervisor;

  const decide = (decision: "APPROVED" | "REJECTED") => {
    if (onDecide) onDecide(decision);
    else if (decision === "REJECTED") onTransition({ ...flow, stage: "cancelled" });
  };

  return (
    <div
      className={cn(
        "w-full max-w-[38rem] rounded-xl border p-5",
        supervisor
          ? "border-neutral-700 bg-neutral-900/50"
          : destructive
            ? "border-red-400/25 bg-red-400/[0.05]"
            : "border-amber-400/20 bg-amber-400/[0.04]",
      )}
    >
      <div className="flex items-center gap-2.5">
        {supervisor ? (
          <ShieldCheck className="h-4 w-4 text-violet-300" aria-hidden="true" />
        ) : (
          <ShieldAlert className={cn("h-4 w-4", destructive ? "text-red-300" : "text-amber-300")} aria-hidden="true" />
        )}
        <p className="text-sm font-medium text-neutral-100">
          {supervisor ? "Persetujuan supervisor diperlukan" : "Tindakan ini butuh persetujuan Anda"}
        </p>
      </div>
      <p className="mt-3 text-sm font-medium leading-6 text-neutral-100">{approval.action}</p>
      <p className="mt-1 text-[13px] leading-6 text-neutral-400">{approval.consequence}</p>

      {approval.reviewing && (
        <dl className="mt-4 space-y-3 border-t border-neutral-800 pt-4">
          <div>
            <dt className="text-xs text-neutral-600">Cakupan</dt>
            <dd className="mt-1 break-all font-mono text-xs text-neutral-300">{approval.scope}</dd>
          </div>
          <div>
            <dt className="text-xs text-neutral-600">Risiko</dt>
            <dd className={cn("mt-1 text-[13px]", supervisor ? "text-neutral-300" : destructive ? "text-red-200" : "text-amber-200")}>{approval.risk}</dd>
          </div>
        </dl>
      )}

      {supervisor ? (
        <div className="mt-4 flex flex-col gap-3 border-t border-neutral-800 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[13px] leading-6 text-neutral-500">
            Keputusan ini hanya dapat diambil supervisor. Anda akan melihat hasilnya di sini
            setelah diputuskan.
          </p>
          {!approval.reviewing && (
            <button
              type="button"
              disabled={!interactive}
              onClick={() => onTransition({ ...flow, approval: { ...approval, reviewing: true } })}
              className="inline-flex h-9 flex-shrink-0 items-center justify-center gap-1.5 rounded-lg border border-neutral-700 bg-transparent px-4 text-[13px] font-medium text-neutral-200 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 disabled:cursor-default disabled:opacity-60 active:scale-[0.98]"
            >
              Tinjau <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      ) : (
      <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          disabled={!interactive}
          onClick={() => decide("REJECTED")}
          className="h-9 rounded-lg border border-neutral-700 bg-transparent px-4 text-[13px] font-medium text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 disabled:cursor-default disabled:opacity-60 active:scale-[0.98]"
        >
          Batal
        </button>
        {!approval.reviewing ? (
          <button
            type="button"
            disabled={!interactive}
            onClick={() => onTransition({ ...flow, approval: { ...approval, reviewing: true } })}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-neutral-100 px-4 text-[13px] font-medium text-neutral-950 transition-[background-color,transform] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 disabled:cursor-default disabled:opacity-60 active:scale-[0.98]"
          >
            Tinjau <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ) : (
          <button
            type="button"
            disabled={!interactive}
            onClick={() => decide("APPROVED")}
            className={cn(
              "h-9 rounded-lg px-4 text-[13px] font-medium transition-[background-color,transform] focus-visible:outline-none focus-visible:ring-2 disabled:cursor-default disabled:opacity-60 active:scale-[0.98]",
              destructive
                ? "bg-red-500 text-white hover:bg-red-400 focus-visible:ring-red-300"
                : "bg-neutral-100 text-neutral-950 hover:bg-white focus-visible:ring-violet-300",
            )}
          >
            {destructive ? "Setujui penghapusan" : "Setujui & jalankan"}
          </button>
        )}
      </div>
      )}
    </div>
  );
}

function ProgressView({ flow }: { flow: TaskFlowState }) {
  const percent = flow.total === 0 ? 0 : Math.round((flow.processed / flow.total) * 100);
  const stepIndex =
    flow.steps.length === 0
      ? 0
      : Math.min(flow.steps.length - 1, Math.floor((flow.processed / Math.max(1, flow.total)) * flow.steps.length));

  return (
    <div className="w-full max-w-[38rem] rounded-xl border border-neutral-800 bg-neutral-900/50 p-5">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm font-medium text-neutral-100">{flow.taskName}…</p>
        <span className="text-sm tabular-nums text-neutral-400">{percent}%</span>
      </div>
      <div
        className="mt-3 h-1.5 overflow-hidden rounded-full bg-neutral-800"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={flow.taskName}
      >
        <div className="h-full rounded-full bg-violet-400 transition-[width] duration-150" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-3 text-[13px] tabular-nums text-neutral-500">
        {flow.processed} / {flow.total} file diproses
      </p>
      {flow.steps.length > 0 && (
        <p className="mt-1.5 flex items-center gap-2 text-[13px] text-violet-300">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-300" aria-hidden="true" />
          {flow.steps[stepIndex]}
        </p>
      )}
    </div>
  );
}

function ResultView({
  flow,
  result,
}: {
  flow: TaskFlowState;
  result: NonNullable<TaskFlowState["result"]>;
}) {
  return (
    <div className="w-full max-w-[38rem] rounded-xl border border-emerald-400/20 bg-emerald-400/[0.04] p-5">
      <p className="flex items-center gap-2 text-sm font-medium text-neutral-100">
        <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden="true" />
        {flow.taskName} selesai
      </p>
      <p className="mt-2 text-[13.5px] leading-6 text-neutral-300">{result.summary}</p>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <ResultStat label="Direncanakan" value={result.planned} />
        <ResultStat label="Dijalankan" value={result.executed} />
        <ResultStat label="Terverifikasi" value={result.verified} />
        <ResultStat label="Gagal" value={result.failed} tone={result.failed > 0 ? "text-red-300" : undefined} />
      </dl>
    </div>
  );
}

function ResultStat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950/60 px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-[11px] text-neutral-600">
        <FileCheck2 className="h-3 w-3" aria-hidden="true" />
        {label}
      </dt>
      <dd className={cn("mt-1 font-mono text-sm tabular-nums text-neutral-100", tone)}>{value}</dd>
    </div>
  );
}

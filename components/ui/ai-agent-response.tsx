"use client";

import * as React from "react";
import {
  AlertCircle,
  Brain,
  Check,
  ChevronDown,
  Code2,
  Command,
  Copy,
  Cpu,
  Database,
  ExternalLink,
  FileCode2,
  FileText,
  Globe,
  Search,
  Terminal,
} from "lucide-react";

import { cn } from "@/lib/utils";

function renderDynamicIcon(icon: any, className?: string): React.ReactNode {
  if (!icon) return null;
  if (React.isValidElement(icon)) return icon;
  if (typeof icon === "function" || typeof icon === "object") {
    return React.createElement(icon, {
      className: cn("size-3.5 shrink-0", className),
      "aria-hidden": "true",
    });
  }
  return null;
}

const CHEVRON_DELAYS = Array.from({ length: 9 }, (_, index) => {
  const row = Math.floor(index / 3);
  const column = index % 3;
  return (column + Math.abs(row - 1)) * 90;
});

export function PixelDotsLoader({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid shrink-0 grid-cols-[repeat(3,3px)] items-center gap-[1.5px]",
        className,
      )}
    >
      {CHEVRON_DELAYS.map((delay, index) => (
        <span
          key={index}
          className="size-[3px] rounded-full bg-foreground/80 motion-reduce:animate-none"
          style={{
            opacity: 0.2,
            animation: `agent-pixel-on 650ms cubic-bezier(0.23, 1, 0.32, 1) ${delay}ms infinite`,
          }}
        />
      ))}
    </span>
  );
}

export interface TerminalCommandProps {
  command: string;
  output?: string;
  exitCode?: number;
  durationMs?: number;
  isRunning?: boolean;
  className?: string;
}

export function TerminalCommand({
  command,
  output,
  exitCode = 0,
  durationMs,
  isRunning = false,
  className,
}: TerminalCommandProps) {
  const [copied, setCopied] = React.useState(false);
  const timeoutRef = React.useRef<number | undefined>(undefined);

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const handleCopy = async () => {
    if (!navigator.clipboard) return;
    const fullText = output ? `$ ${command}\n\n${output}` : `$ ${command}`;
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      return;
    }
  };

  return (
    <div
      className={cn(
        "flex w-full flex-col overflow-hidden rounded-lg border border-border/80 bg-card font-mono text-[11.5px] shadow-sm",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border/70 bg-muted/40 px-2.5 py-1.5 text-[11px]">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Terminal className="size-3.5 shrink-0 text-violet-400" aria-hidden="true" />
          <span className="select-none font-bold text-muted-foreground/60">$</span>
          <span className="truncate font-semibold tracking-tight text-foreground">
            {command}
          </span>
        </div>

        <div className="ml-2 flex shrink-0 items-center gap-2">
          {durationMs !== undefined && (
            <span className="text-[11px] tabular-nums text-muted-foreground/60">
              {durationMs}ms
            </span>
          )}
          {isRunning ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-violet-500/10 px-2 py-0.5 text-[10.5px] font-medium text-violet-300">
              <span className="size-1.5 animate-pulse rounded-full bg-violet-400" />
              sedang berjalan
            </span>
          ) : exitCode === 0 ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10.5px] font-medium tabular-nums text-emerald-300">
              selesai
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 px-1.5 py-0.5 text-[10.5px] font-medium tabular-nums text-rose-300">
              exit {exitCode}
            </span>
          )}
          <button
            type="button"
            onClick={handleCopy}
            aria-label={copied ? "Copied command and output" : "Copy command"}
            className="flex items-center rounded-sm px-1 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.96]"
          >
            {copied ? (
              <Check className="size-3 text-emerald-400" aria-hidden="true" />
            ) : (
              <Copy className="size-3" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {output && (
        <div className="overflow-x-auto bg-muted/20 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
          <code className="flex flex-col whitespace-pre font-mono">
            {output.split("\n").map((line, index) => {
              const isPass =
                line.includes("✓") || line.includes("PASS") || line.includes("passed");
              const isFail =
                line.includes("FAIL") || line.includes("Error") || line.includes("failed");
              const isWarn = line.includes("WARN") || line.includes("warning");

              return (
                <span
                  key={index}
                  className={cn(
                    isPass && "font-medium text-emerald-300",
                    isFail && "font-medium text-rose-300",
                    isWarn && "text-amber-300",
                    !isPass && !isFail && !isWarn && "text-muted-foreground",
                  )}
                >
                  {line}
                </span>
              );
            })}
          </code>
        </div>
      )}
    </div>
  );
}

export type DiffRow = {
  old?: number | null;
  cur?: number | null;
  type: "add" | "del" | "ctx";
  text: string;
};

export interface FileDiffProps {
  file: string;
  rows: DiffRow[];
  className?: string;
}

export function FileDiff({ file, rows = [], className }: FileDiffProps) {
  const [copied, setCopied] = React.useState(false);
  const timeoutRef = React.useRef<number | undefined>(undefined);
  const added = rows.filter((row) => row.type === "add").length;
  const removed = rows.filter((row) => row.type === "del").length;

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const handleCopy = async () => {
    if (!navigator.clipboard) return;
    const textContent = rows
      .map((row) => `${row.type === "add" ? "+" : row.type === "del" ? "-" : " "} ${row.text}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(textContent);
      setCopied(true);
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      return;
    }
  };

  return (
    <div
      className={cn(
        "flex w-full flex-col overflow-hidden rounded-lg border border-border/80 bg-card font-mono text-[11.5px] shadow-sm",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border/70 bg-muted/40 px-2.5 py-1.5 text-[11px]">
        <div className="flex min-w-0 items-center gap-2">
          <Code2 className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate font-medium tracking-tight text-foreground">{file}</span>
        </div>
        <div className="ml-2 flex shrink-0 items-center gap-2">
          <div className="flex items-center gap-1.5 tabular-nums text-[11px] font-semibold">
            {added > 0 && <span className="text-emerald-300">+{added}</span>}
            {removed > 0 && <span className="text-rose-300">-{removed}</span>}
          </div>
          <button
            type="button"
            onClick={handleCopy}
            aria-label={copied ? "Copied diff" : "Copy diff to clipboard"}
            className="flex items-center rounded-sm px-1 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.96]"
          >
            {copied ? (
              <Check className="size-3 text-emerald-400" aria-hidden="true" />
            ) : (
              <Copy className="size-3" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      <div className="relative flex flex-col overflow-x-auto py-1.5 leading-[21px]">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute bottom-0 left-[70px] top-0 z-[1] w-px bg-border/60"
        />
        {rows.map((row, index) => (
          <div
            key={index}
            className={cn(
              "group relative grid grid-cols-[34px_34px_20px_1fr] items-stretch transition-colors duration-100",
              row.type === "add" && "bg-emerald-500/10 text-emerald-100",
              row.type === "del" && "bg-rose-500/10 text-rose-100",
              row.type === "ctx" && "text-muted-foreground",
            )}
          >
            {row.type === "add" && (
              <span className="absolute bottom-0 left-0 top-0 w-[3px] bg-emerald-500" aria-hidden="true" />
            )}
            {row.type === "del" && (
              <span
                className="absolute bottom-0 left-0 top-0 w-[3px]"
                aria-hidden="true"
                style={{
                  background:
                    "repeating-linear-gradient(45deg, #f43f5e 0, #f43f5e 1.5px, transparent 1.5px, transparent 3px)",
                }}
              />
            )}
            <span
              className={cn(
                "select-none pr-2 text-right text-[10.5px] tabular-nums",
                row.type === "del" ? "font-semibold text-rose-300" : "text-muted-foreground/60",
              )}
            >
              {row.old ?? ""}
            </span>
            <span
              className={cn(
                "select-none pr-2 text-right text-[10.5px] tabular-nums",
                row.type === "add" ? "font-semibold text-emerald-300" : "text-muted-foreground/60",
              )}
            >
              {row.cur ?? ""}
            </span>
            <span
              className={cn(
                "select-none text-center text-[11px] font-bold",
                row.type === "add" && "text-emerald-300",
                row.type === "del" && "text-rose-300",
              )}
            >
              {row.type === "add" ? "+" : row.type === "del" ? "-" : ""}
            </span>
            <code
              className={cn(
                "whitespace-pre pl-1 pr-3 text-[11.5px] font-mono",
                row.type === "add" && "font-medium text-foreground",
                row.type === "del" && "text-foreground line-through opacity-80",
                row.type === "ctx" && "text-muted-foreground",
              )}
            >
              {row.text}
            </code>
          </div>
        ))}
      </div>
    </div>
  );
}

export type TraceNodeType =
  | "reasoning"
  | "step"
  | "search"
  | "tool"
  | "terminal"
  | "diffs"
  | (string & {});

export type DetailLine = {
  text: string;
  tone?: "add" | "del" | "ctx" | "muted" | "error";
};

export interface ToolDefinition<TArgs = any, TResult = any> {
  name: string;
  label?: string | ((args: TArgs) => string);
  icon?: any;
  iconClassName?: string;
  formatChip?: (args: TArgs, result?: TResult) => string;
  monoChip?: boolean;
  renderCustomContent?: (props: {
    args?: TArgs;
    result?: TResult;
    node: TraceNode<TArgs, TResult>;
  }) => React.ReactNode;
}

export type TraceNode<TArgs = any, TResult = any> = {
  id?: string;
  type: TraceNodeType;
  toolName?: string;
  sentences?: string[];
  delays?: number[];
  durationSeconds?: number;
  primary?: string;
  secondary?: string;
  mono?: boolean;
  icon?: any;
  iconClassName?: string;
  status?: "pending" | "running" | "completed" | "failed";
  args?: TArgs;
  result?: TResult;
  command?: string;
  output?: string;
  exitCode?: number;
  durationMs?: number;
  add?: number;
  del?: number;
  diffRows?: DiffRow[];
  diffFile?: string;
  codeSnippet?: string;
  details?: DetailLine[];
  sources?: { name: string; url?: string }[];
  renderContent?: () => React.ReactNode;
};

export type AgentPhase = {
  trace: TraceNode[];
  message?: string;
};

export const DEFAULT_TOOL_REGISTRY: Record<string, ToolDefinition<any, any>> = {
  read_file: {
    name: "read_file",
    label: "Read",
    icon: FileText,
    iconClassName: "text-muted-foreground/80",
    monoChip: true,
  },
  edit_file: {
    name: "edit_file",
    label: "Edit",
    icon: FileCode2,
    iconClassName: "text-amber-400",
    monoChip: true,
  },
  execute_command: {
    name: "execute_command",
    label: "Run",
    icon: Terminal,
    iconClassName: "text-violet-400",
    monoChip: true,
  },
  search_web: {
    name: "search_web",
    label: "Search",
    icon: Search,
    iconClassName: "text-blue-400",
  },
  query_database: {
    name: "query_database",
    label: "SQL Query",
    icon: Database,
    iconClassName: "text-emerald-400",
    monoChip: true,
  },
};

function PhaseStreamingText({
  text,
  onComplete,
  reducedMotion = false,
}: {
  text: string;
  onComplete: () => void;
  reducedMotion?: boolean;
}) {
  const [shown, setShown] = React.useState("");
  const completedRef = React.useRef(false);
  const onCompleteRef = React.useRef(onComplete);
  onCompleteRef.current = onComplete;

  React.useEffect(() => {
    completedRef.current = false;

    const complete = () => {
      if (completedRef.current) return;
      completedRef.current = true;
      onCompleteRef.current();
    };

    if (reducedMotion) {
      setShown(text);
      complete();
      return;
    }

    let index = 0;
    setShown("");
    const timer = window.setInterval(() => {
      index += 2;
      setShown(text.slice(0, index));
      if (index >= text.length) {
        window.clearInterval(timer);
        complete();
      }
    }, 18);
    return () => window.clearInterval(timer);
  }, [reducedMotion, text]);

  return (
    <div className="select-text whitespace-pre-line text-[14px] leading-relaxed text-foreground/90">
      {shown}
    </div>
  );
}

interface NestedReasoningBlockProps {
  sentences: string[];
  delays?: number[];
  isActive: boolean;
  isFinished: boolean;
  durationSeconds?: number;
  onFinished?: () => void;
}

export function NestedReasoningBlock({
  sentences,
  delays,
  isActive,
  isFinished,
  durationSeconds = 4.2,
  onFinished,
}: NestedReasoningBlockProps) {
  const [revealedCount, setRevealedCount] = React.useState(
    isFinished ? sentences.length : 0,
  );
  const [manualOpen, setManualOpen] = React.useState(false);
  const [fade, setFade] = React.useState({ top: false, bottom: true });
  const viewportRef = React.useRef<HTMLDivElement>(null);
  const onFinishedRef = React.useRef(onFinished);
  onFinishedRef.current = onFinished;

  React.useEffect(() => {
    if (isFinished) setRevealedCount(sentences.length);
  }, [isFinished, sentences.length]);

  React.useEffect(() => {
    if (!isActive || isFinished) return;
    if (sentences.length === 0) {
      onFinishedRef.current?.();
      return;
    }

    const cadence = delays ?? sentences.map(() => 450);
    const timers: number[] = [];
    let cumulative = 0;

    cadence.forEach((delay, index) => {
      cumulative += delay;
      timers.push(
        window.setTimeout(() => setRevealedCount(index + 1), cumulative),
      );
    });
    timers.push(
      window.setTimeout(() => onFinishedRef.current?.(), cumulative + 240),
    );

    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [delays, isActive, isFinished, sentences]);

  const expanded = isFinished ? manualOpen : isActive;
  const count = isFinished ? sentences.length : revealedCount;
  const contentHeight = count > 0 ? count * 42 + (count - 1) * 8 : 0;
  const capped = contentHeight > 184;
  const viewHeight = capped ? 184 : contentHeight;
  const scrollable = isFinished && manualOpen;
  const translate = scrollable || !capped ? 0 : Math.max(184 - 18 - contentHeight, -contentHeight);
  const mask = capped
    ? "linear-gradient(to bottom, transparent 0, #000 18px, #000 calc(100% - 18px), transparent 100%)"
    : "none";

  const onScroll = () => {
    const element = viewportRef.current;
    if (!element) return;
    setFade({
      top: element.scrollTop > 1,
      bottom: element.scrollTop + element.clientHeight < element.scrollHeight - 1,
    });
  };

  return (
    <div className="my-0.5 flex w-full flex-col" style={{ animation: "agent-fade 280ms cubic-bezier(0.23,1,0.32,1) both" }}>
      <button
        type="button"
        disabled={!isFinished}
        aria-expanded={expanded}
        onClick={() => isFinished && setManualOpen((value) => !value)}
        className={cn(
          "group/row relative flex h-7 w-full items-center gap-2 rounded-md px-1.5 text-left text-[12px] transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isFinished ? "cursor-pointer hover:bg-muted/60 active:scale-[0.98]" : "cursor-default",
        )}
      >
        <span className="relative flex size-4 shrink-0 items-center justify-center text-muted-foreground">
          <Brain
            aria-hidden="true"
            className={cn(
              "size-3.5 opacity-75 transition-opacity duration-150",
              isFinished && "group-hover/row:opacity-0",
              manualOpen && "opacity-0",
            )}
          />
          {isFinished && (
            <ChevronDown
              aria-hidden="true"
              className={cn(
                "absolute size-3.5 opacity-0 transition-transform duration-200 group-hover/row:opacity-100",
                manualOpen ? "rotate-0 opacity-100" : "-rotate-90",
              )}
            />
          )}
        </span>
        <span className="text-[12px] font-medium">
          {isFinished ? (
            <span className="text-foreground">
              Memproses selama <span className="font-mono text-[11.5px] tabular-nums">{durationSeconds}s</span>
            </span>
          ) : (
            <span
              className="bg-clip-text font-medium text-transparent"
              style={{
                backgroundImage:
                  "linear-gradient(90deg, rgb(163 163 163 / .65) 35%, rgb(255 255 255 / .95) 50%, rgb(163 163 163 / .65) 65%)",
                backgroundSize: "200% 100%",
                animation: "agent-shimmer 1.8s linear infinite",
              }}
            >
              Memahami permintaan...
            </span>
          )}
        </span>
      </button>

      <div
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)]",
          expanded ? "grid-rows-[1fr] opacity-100" : "pointer-events-none grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="mb-1.5 ml-2.5 border-l border-border/70 py-0.5 pl-2.5">
            <div
              ref={viewportRef}
              className={cn(
                "pr-1 transition-[height] duration-300 ease-out",
                scrollable && "overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
                !scrollable && "overflow-hidden",
              )}
              style={{
                height: `${viewHeight}px`,
                WebkitMaskImage: mask,
                maskImage: mask,
              }}
              onScroll={scrollable ? onScroll : undefined}
            >
              <div
                className="flex flex-col gap-2 transition-transform duration-300 ease-out will-change-transform"
                style={{ transform: `translateY(${translate}px)` }}
              >
                {sentences.slice(0, count).map((sentence, index) => (
                  <p
                    key={index}
                    className="m-0 line-clamp-2 h-[42px] overflow-hidden text-[13px] font-normal leading-[21px] tracking-tight text-muted-foreground"
                    style={{ animation: "agent-fade 250ms cubic-bezier(0.23,1,0.32,1) both" }}
                  >
                    {sentence}
                  </p>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface TracePillRowProps {
  node: TraceNode;
  isActive: boolean;
  isFinished: boolean;
  toolRegistry?: Record<string, ToolDefinition<any, any>>;
}

function TracePillRow({
  node,
  isActive,
  isFinished,
  toolRegistry = DEFAULT_TOOL_REGISTRY,
}: TracePillRowProps) {
  const [open, setOpen] = React.useState(false);
  const toolDef = node.toolName ? toolRegistry[node.toolName] : undefined;
  const isCommandNode = Boolean(
    node.command || node.type === "terminal" || node.type === "command",
  );
  const hasDetails = Boolean(
    isCommandNode ||
      node.renderContent ||
      toolDef?.renderCustomContent ||
      node.diffRows ||
      node.codeSnippet ||
      (node.details && node.details.length > 0) ||
      (node.sources && node.sources.length > 0) ||
      node.args ||
      node.result,
  );
  const primaryText =
    node.primary ||
    (isCommandNode ? "Run" : undefined) ||
    (typeof toolDef?.label === "function" ? toolDef.label(node.args) : toolDef?.label) ||
    toolDef?.name ||
    node.type;
  const secondaryText =
    node.secondary ||
    node.command ||
    (toolDef?.formatChip ? toolDef.formatChip(node.args, node.result) : undefined) ||
    (typeof node.args === "string" ? node.args : undefined);
  const isMono = node.mono ?? (isCommandNode || Boolean(toolDef?.monoChip));

  const renderIcon = () => {
    if (isActive) {
      return (
        <span
          aria-hidden="true"
          className="size-3.5 shrink-0 animate-spin rounded-full border-[1.5px] border-muted-foreground/30 border-t-foreground"
        />
      );
    }
    if (node.status === "failed" || (node.exitCode !== undefined && node.exitCode > 0)) {
      return <AlertCircle className="size-3.5 shrink-0 text-rose-400" aria-hidden="true" />;
    }
    if (node.icon) return renderDynamicIcon(node.icon, node.iconClassName);
    if (toolDef?.icon) return renderDynamicIcon(toolDef.icon, toolDef.iconClassName);

    const semanticKey = `${node.primary || ""} ${node.toolName || ""} ${node.type || ""} ${node.command || ""}`.toLowerCase();
    if (semanticKey.includes("read") || semanticKey.includes("inspect") || semanticKey.includes("parse")) {
      return <FileText className="size-3.5 shrink-0 text-muted-foreground/80" aria-hidden="true" />;
    }
    if (semanticKey.includes("edit") || semanticKey.includes("write") || semanticKey.includes("patch") || semanticKey.includes("create")) {
      return <FileCode2 className="size-3.5 shrink-0 text-amber-400" aria-hidden="true" />;
    }
    if (isCommandNode || semanticKey.includes("run") || semanticKey.includes("test") || semanticKey.includes("compile") || semanticKey.includes("exec")) {
      return <Terminal className="size-3.5 shrink-0 text-violet-400" aria-hidden="true" />;
    }
    if (semanticKey.includes("search") || semanticKey.includes("query") || semanticKey.includes("lookup")) {
      return <Search className="size-3.5 shrink-0 text-blue-400" aria-hidden="true" />;
    }
    if (semanticKey.includes("db") || semanticKey.includes("database") || semanticKey.includes("sql")) {
      return <Database className="size-3.5 shrink-0 text-emerald-400" aria-hidden="true" />;
    }
    if (semanticKey.includes("deploy") || semanticKey.includes("cluster")) {
      return <Cpu className="size-3.5 shrink-0 text-sky-400" aria-hidden="true" />;
    }
    if (node.type === "step") {
      return <Check className="size-3.5 shrink-0 text-emerald-400" aria-hidden="true" />;
    }
    return <Command className="size-3.5 shrink-0 text-muted-foreground/80" aria-hidden="true" />;
  };

  return (
    <div className="my-0.5 flex flex-col" style={{ animation: "agent-fade 280ms cubic-bezier(0.23,1,0.32,1) both" }}>
      <button
        type="button"
        disabled={!hasDetails}
        aria-expanded={open}
        onClick={() => hasDetails && setOpen((value) => !value)}
        className={cn(
          "group/row relative flex h-7 w-full items-center gap-2 rounded-md px-1.5 text-left text-[12px] transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          hasDetails ? "cursor-pointer hover:bg-muted/60 active:scale-[0.98]" : "cursor-default",
        )}
      >
        <span className="relative flex size-4 shrink-0 items-center justify-center text-muted-foreground">
          <span
            className={cn(
              "flex items-center justify-center transition-opacity duration-150",
              hasDetails && "group-hover/row:opacity-0",
              open && "opacity-0",
            )}
          >
            {renderIcon()}
          </span>
          {hasDetails && (
            <ChevronDown
              aria-hidden="true"
              className={cn(
                "absolute size-3.5 opacity-0 transition-transform duration-200 group-hover/row:opacity-100",
                open ? "rotate-0 opacity-100" : "-rotate-90",
              )}
            />
          )}
        </span>
        <span className="shrink-0 text-[12px] font-medium tracking-tight text-foreground">
          {primaryText}
        </span>
        {secondaryText && (
          <span
            className={cn(
              "inline-flex h-5 min-w-0 max-w-[65%] items-center truncate rounded-md border border-border/40 bg-muted/80 px-1.5 text-[11px] text-muted-foreground transition-colors group-hover/row:border-border/80 group-hover/row:text-foreground",
              isMono ? "font-mono" : "font-sans",
            )}
          >
            <span className="truncate">{secondaryText}</span>
          </span>
        )}
        {(node.add !== undefined || node.del !== undefined) && (
          <span className="ml-auto flex shrink-0 items-center gap-1 font-mono text-[11px] tabular-nums">
            {node.add !== undefined && node.add > 0 && <span className="font-medium text-emerald-300">+{node.add}</span>}
            {node.del !== undefined && node.del > 0 && <span className="font-medium text-rose-300">-{node.del}</span>}
          </span>
        )}
      </button>

      {hasDetails && (
        <div
          className={cn(
            "grid transition-[grid-template-rows,opacity] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)]",
            open ? "grid-rows-[1fr] opacity-100" : "pointer-events-none grid-rows-[0fr] opacity-0",
          )}
        >
          <div className="min-h-0 overflow-hidden">
            <div className="mb-1.5 ml-2.5 flex flex-col gap-1.5 border-l border-border/70 py-0.5 pl-2.5">
              {node.renderContent
                ? node.renderContent()
                : toolDef?.renderCustomContent
                  ? toolDef.renderCustomContent({ args: node.args, result: node.result, node })
                  : null}
              {isCommandNode && node.command && (
                <TerminalCommand
                  command={node.command}
                  output={node.output}
                  exitCode={node.exitCode ?? 0}
                  durationMs={node.durationMs}
                  isRunning={isActive}
                />
              )}
              {!isCommandNode && node.diffRows && (
                <FileDiff
                  file={node.diffFile || node.secondary || "patch.ts"}
                  rows={node.diffRows}
                />
              )}
              {!isCommandNode && node.details && node.details.length > 0 && (
                <div className="flex flex-col gap-1">
                  {node.details.map((line, index) => (
                    <span
                      key={index}
                      className={cn(
                        "text-[11.5px] leading-relaxed",
                        line.tone === "add" && "font-mono text-emerald-300",
                        line.tone === "del" && "font-mono text-rose-300",
                        line.tone === "ctx" && "font-mono text-muted-foreground",
                        line.tone === "error" && "font-medium text-rose-300",
                        (!line.tone || line.tone === "muted") && "text-muted-foreground",
                      )}
                    >
                      {line.text}
                    </span>
                  ))}
                </div>
              )}
              {!isCommandNode && !node.diffRows && node.codeSnippet && (
                <div className="overflow-x-auto rounded-lg border border-border/70 bg-muted/40 p-2.5 font-mono text-[11px] leading-relaxed text-foreground">
                  <pre className="whitespace-pre">{node.codeSnippet}</pre>
                </div>
              )}
              {node.sources && node.sources.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  {node.sources.map((source, index) => (
                    <a
                      key={index}
                      href={source.url || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background px-2.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-border hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <Globe className="size-2.5 opacity-70" aria-hidden="true" />
                      <span>{source.name}</span>
                      <ExternalLink className="size-2.5 opacity-50" aria-hidden="true" />
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export interface ThinkingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  nodes?: TraceNode[];
  tools?: Record<string, ToolDefinition<any, any>>;
  autoPlay?: boolean;
  /**
   * When set, decides whether the "working" indicator is shown, so a real
   * in-flight task keeps the indicator up even after the trace renders.
   */
  running?: boolean;
  defaultExpanded?: boolean;
  workingLabel?: string;
  reducedMotion?: boolean;
  onSettled?: () => void;
}

export const ThinkingState = React.forwardRef<HTMLDivElement, ThinkingStateProps>(
  (
    {
      nodes = [],
      tools = DEFAULT_TOOL_REGISTRY,
      autoPlay = true,
      running,
      defaultExpanded,
      workingLabel = "BERESIN sedang bekerja...",
      reducedMotion = false,
      onSettled,
      className,
      style,
      ...props
    },
    ref,
  ) => {
    const totalNodes = nodes.length;
    const shouldAnimate = autoPlay && !reducedMotion;
    const [activeIndex, setActiveIndex] = React.useState(shouldAnimate ? 0 : totalNodes);
    const [isWorking, setIsWorking] = React.useState(shouldAnimate && totalNodes > 0);
    const [manualExpanded, setManualExpanded] = React.useState<boolean | null>(
      defaultExpanded !== undefined ? defaultExpanded : null,
    );
    const [elapsedSeconds, setElapsedSeconds] = React.useState(0);
    const startTimeRef = React.useRef(Date.now());
    const isWorkingRef = React.useRef(isWorking);
    const settledRef = React.useRef(false);
    const onSettledRef = React.useRef(onSettled);
    onSettledRef.current = onSettled;
    isWorkingRef.current = isWorking;

    React.useEffect(() => {
      if (!autoPlay) return;
      startTimeRef.current = Date.now();
      settledRef.current = false;
      setActiveIndex(!reducedMotion && totalNodes > 0 ? 0 : totalNodes);
      setIsWorking(!reducedMotion && totalNodes > 0);
      setElapsedSeconds(0);
    }, [autoPlay, reducedMotion, totalNodes]);

    React.useEffect(() => {
      if (!autoPlay || reducedMotion) return;
      const timer = window.setInterval(() => {
        if (!isWorkingRef.current) return;
        setElapsedSeconds(Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000)));
      }, 250);
      return () => window.clearInterval(timer);
    }, [autoPlay, reducedMotion]);

    React.useEffect(() => {
      if (!autoPlay || !isWorking || activeIndex < totalNodes) return;
      setIsWorking(false);
      setElapsedSeconds(Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000)));
    }, [activeIndex, autoPlay, isWorking, totalNodes]);

    React.useEffect(() => {
      if (isWorking || !autoPlay || settledRef.current) return;
      settledRef.current = true;
      onSettledRef.current?.();
    }, [autoPlay, isWorking]);

    const advanceStep = React.useCallback(() => {
      setActiveIndex((previous) => Math.min(previous + 1, totalNodes));
    }, [totalNodes]);

    React.useEffect(() => {
      if (!autoPlay || reducedMotion || !isWorking || activeIndex >= totalNodes) return;
      const currentNode = nodes[activeIndex];
      if (currentNode?.type === "reasoning") return;
      const delay =
        currentNode?.type === "terminal" || currentNode?.type === "tool"
          ? 800
          : currentNode?.type === "search"
            ? 900
            : 650;
      const timer = window.setTimeout(advanceStep, delay);
      return () => window.clearTimeout(timer);
    }, [activeIndex, autoPlay, isWorking, nodes, reducedMotion, totalNodes, advanceStep]);

    const isWorkingDisplay = running ?? isWorking;
    const isGlobalExpanded = manualExpanded !== null ? manualExpanded : isWorkingDisplay;

    return (
      <div
        ref={ref}
        className={cn("flex w-full flex-col select-none font-sans text-foreground", className)}
        style={style}
        {...props}
      >
        <button
          type="button"
          aria-expanded={isGlobalExpanded}
          onClick={() => setManualExpanded((previous) => !(previous !== null ? previous : isWorkingDisplay))}
          className="group flex w-fit cursor-pointer items-center gap-1.5 rounded-sm bg-transparent p-0 text-left text-[13.5px] font-normal leading-relaxed text-muted-foreground/75 transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {isWorkingDisplay && <PixelDotsLoader />}
          <span className="text-[13.5px] font-normal">
            {isWorkingDisplay ? (
              <span
                className="bg-clip-text font-medium text-transparent"
                style={{
                  backgroundImage:
                    "linear-gradient(90deg, rgb(163 163 163 / .65) 35%, rgb(255 255 255 / .95) 50%, rgb(163 163 163 / .65) 65%)",
                  backgroundSize: "200% 100%",
                  animation: "agent-shimmer 1.5s linear infinite",
                }}
              >
                {workingLabel}
              </span>
            ) : (
              <span>
                Selesai dalam <span className="font-mono text-[12px] tabular-nums">{elapsedSeconds}</span>{" "}
                {elapsedSeconds === 1 ? "detik" : "detik"}
              </span>
            )}
          </span>
          <ChevronDown
            aria-hidden="true"
            className={cn(
              "size-3 opacity-30 transition-transform duration-300 group-hover:opacity-80",
              isGlobalExpanded ? "rotate-180" : "rotate-0",
            )}
          />
        </button>

        <div
          className={cn(
            "grid transition-[grid-template-rows,opacity] duration-300 ease-out",
            isGlobalExpanded
              ? "grid-rows-[1fr] opacity-100"
              : "pointer-events-none grid-rows-[0fr] opacity-0",
          )}
        >
          <div className="min-h-0 overflow-hidden">
            <div className="ml-2 flex flex-col gap-0.5 border-l border-border/60 py-0.5 pl-2">
              {nodes.slice(0, Math.min(activeIndex + 1, totalNodes)).map((node, index) => {
                const isNodeActive = index === activeIndex && isWorking;
                const isNodeFinished = index < activeIndex || !isWorking;
                if (node.type === "reasoning" && node.sentences) {
                  return (
                    <NestedReasoningBlock
                      key={`${node.id || index}-${isNodeActive ? "active" : "done"}`}
                      sentences={node.sentences}
                      delays={node.delays}
                      durationSeconds={node.durationSeconds}
                      isActive={isNodeActive}
                      isFinished={isNodeFinished}
                      onFinished={advanceStep}
                    />
                  );
                }
                return (
                  <TracePillRow
                    key={`${node.id || index}-${isNodeActive ? "active" : "done"}`}
                    node={node}
                    isActive={isNodeActive}
                    isFinished={isNodeFinished}
                    toolRegistry={tools}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
ThinkingState.displayName = "ThinkingState";

export interface AgentWorkflowProps extends React.HTMLAttributes<HTMLDivElement> {
  phases: AgentPhase[];
  tools?: Record<string, ToolDefinition<any, any>>;
  workingLabel?: string;
  reducedMotion?: boolean;
  onComplete?: () => void;
}

export function AgentWorkflow({
  phases = [],
  tools,
  workingLabel = "BERESIN sedang bekerja...",
  reducedMotion = false,
  onComplete,
  className,
  ...props
}: AgentWorkflowProps) {
  const [currentPhaseIndex, setCurrentPhaseIndex] = React.useState(0);
  const [phaseStatus, setPhaseStatus] = React.useState<"trace" | "message">("trace");
  const completedRef = React.useRef(false);
  const traceSettledRef = React.useRef(false);
  const onCompleteRef = React.useRef(onComplete);
  onCompleteRef.current = onComplete;

  const finish = React.useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    onCompleteRef.current?.();
  }, []);

  const handleTraceSettled = React.useCallback(
    (index: number) => {
      if (index !== currentPhaseIndex || traceSettledRef.current) return;
      traceSettledRef.current = true;
      if (phases[index]?.message) {
        setPhaseStatus("message");
      } else if (index < phases.length - 1) {
        traceSettledRef.current = false;
        setCurrentPhaseIndex((previous) => previous + 1);
        setPhaseStatus("trace");
      } else {
        finish();
      }
    },
    [currentPhaseIndex, finish, phases],
  );

  const handleMessageCompleted = React.useCallback(
    (index: number) => {
      if (index !== currentPhaseIndex) return;
      if (index < phases.length - 1) {
        traceSettledRef.current = false;
        setCurrentPhaseIndex((previous) => previous + 1);
        setPhaseStatus("trace");
      } else {
        finish();
      }
    },
    [currentPhaseIndex, finish, phases],
  );

  React.useEffect(() => {
    if (phases.length === 0) finish();
  }, [finish, phases.length]);

  return (
    <div className={cn("flex w-full flex-col gap-4", className)} {...props}>
      {phases.map((phase, index) => {
        if (index > currentPhaseIndex) return null;
        const isCurrentPhase = index === currentPhaseIndex;
        const shouldPlayTrace = isCurrentPhase && phaseStatus === "trace";
        const traceFinished = !isCurrentPhase || phaseStatus === "message";
        const showMessage = traceFinished && Boolean(phase.message);
        const streamMessage = isCurrentPhase && phaseStatus === "message";

        return (
          <div key={index} className="flex flex-col gap-1">
            <ThinkingState
              key={`${index}-${shouldPlayTrace ? "playing" : "settled"}`}
              nodes={phase.trace}
              tools={tools}
              autoPlay={shouldPlayTrace}
              workingLabel={workingLabel}
              reducedMotion={reducedMotion}
              onSettled={() => handleTraceSettled(index)}
            />
            {showMessage && phase.message && (
              <div className="pt-0" style={{ animation: "agent-fade 300ms ease-out both" }}>
                {streamMessage ? (
                  <PhaseStreamingText
                    text={phase.message}
                    reducedMotion={reducedMotion}
                    onComplete={() => handleMessageCompleted(index)}
                  />
                ) : (
                  <div className="select-text whitespace-pre-line text-[14px] leading-relaxed text-foreground/90">
                    {phase.message}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

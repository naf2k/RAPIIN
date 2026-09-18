"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { HTMLAttributes } from "react";
import {
  CheckCheck,
  ChevronDown,
  Copy,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { cn } from "@/lib/utils";

const DEFAULT_TEXT =
  "Aku menemukan beberapa file yang bisa dirapikan. BERESIN akan membaca metadata, mengelompokkan dokumen berdasarkan tipe dan tahun, lalu memeriksa duplikat sebelum menampilkan rekomendasi yang aman.";

const SOURCE_IMAGES = {
  scoop:
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%231f7a5f'/%3E%3Cpath d='M20 36c0 7 5.4 12 12 12s12-5 12-12H20Z' fill='%23fff'/%3E%3Ccircle cx='32' cy='25' r='11' fill='%23bff3dd'/%3E%3Cpath d='M24 24c4-7 13-7 17 0' fill='none' stroke='%231f7a5f' stroke-width='4' stroke-linecap='round'/%3E%3C/svg%3E",
  trends:
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%232f6fec'/%3E%3Cpath d='M15 43 27 31l8 7 14-18' fill='none' stroke='%23fff' stroke-width='7' stroke-linecap='round' stroke-linejoin='round'/%3E%3Ccircle cx='49' cy='20' r='5' fill='%23bfe0ff'/%3E%3C/svg%3E",
  market:
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23e56d24'/%3E%3Cpath d='M17 45V25h8v20h-8Zm11 0V16h8v29h-8Zm11 0V30h8v15h-8Z' fill='%23fff'/%3E%3Cpath d='M16 49h32' stroke='%23ffd6b8' stroke-width='4' stroke-linecap='round'/%3E%3C/svg%3E",
};

export interface StreamingSource {
  name: string;
  domain: string;
  href: string;
  image?: string;
}

export const DEFAULT_STREAMING_SOURCES: StreamingSource[] = [
  {
    name: "BERESIN Product Guide",
    domain: "product.beresin",
    href: "#product-guide",
    image: SOURCE_IMAGES.scoop,
  },
  {
    name: "File Intelligence",
    domain: "beresin.local/files",
    href: "#file-intelligence",
    image: SOURCE_IMAGES.trends,
  },
  {
    name: "Permission Model",
    domain: "beresin.local/policy",
    href: "#permission-model",
    image: SOURCE_IMAGES.market,
  },
];

const DEFAULT_FOLLOW_UPS = [
  "Tampilkan rekomendasi folder",
  "Cek file duplikat",
];

export interface StreamingTextProps extends HTMLAttributes<HTMLDivElement> {
  text?: string;
  sources?: StreamingSource[];
  followUps?: string[];
  isStreaming?: boolean;
  speed?: number;
  /**
   * "simulated" types the text out on a timer; "live" renders exactly the text
   * it is given, so real streamed deltas appear as they arrive.
   */
  mode?: "simulated" | "live";
  /**
   * "markdown" keeps the model's line breaks, turns "- "/"1. " lines into list
   * rows, and renders **bold** and `code` instead of printing the markers.
   */
  format?: "plain" | "markdown";
  onComplete?: () => void;
  onFollowUp?: (text: string) => void;
  onRetry?: () => void;
}

interface Token {
  text: string;
  cite?: boolean;
}

interface Segment {
  text: string;
  bold: boolean;
  code: boolean;
  cite?: boolean;
  lineBreak?: boolean;
}

interface MarkdownLine {
  marker: string | null;
  heading: number | null;
  segments: Segment[];
}

/** Resolves inline `**bold**` and `` `code` `` markers across streamed tokens. */
function toSegments(tokens: Token[]): Segment[] {
  const out: Segment[] = [];
  let bold = false;
  let code = false;

  for (const token of tokens) {
    if (token.cite) {
      out.push({ text: "", bold, code, cite: true });
      continue;
    }
    const parts = token.text.split("\n");
    parts.forEach((part, partIndex) => {
      if (partIndex > 0) out.push({ text: "", bold, code, lineBreak: true });

      let cursor = 0;
      while (cursor < part.length) {
        const boldAt = part.indexOf("**", cursor);
        const codeAt = part.indexOf("`", cursor);
        let next = -1;
        let kind: "bold" | "code" | null = null;
        if (boldAt !== -1 && (codeAt === -1 || boldAt < codeAt)) {
          next = boldAt;
          kind = "bold";
        } else if (codeAt !== -1) {
          next = codeAt;
          kind = "code";
        }
        if (next === -1) {
          out.push({ text: part.slice(cursor), bold, code });
          break;
        }
        if (next > cursor) out.push({ text: part.slice(cursor, next), bold, code });
        if (kind === "bold") {
          bold = !bold;
          cursor = next + 2;
        } else {
          code = !code;
          cursor = next + 1;
        }
      }
    });
  }

  return out;
}

// The tokenizer splits on whitespace, so a marker often arrives as its own
// token ("-") with the separating space in the next one.
const BULLET = /^\s*([-*•]|\d+[.)])(?:\s+|$)/;
const HEADING = /^\s*(#{1,6})(?:\s+|$)/;

/** Groups segments into rendered lines and pulls out any list marker. */
function toLines(segments: Segment[]): MarkdownLine[] {
  const lines: MarkdownLine[] = [];
  let current: Segment[] = [];

  const flush = () => {
    if (current.length === 0) {
      lines.push({ marker: null, heading: null, segments: [] });
      return;
    }
    const firstIndex = current.findIndex((segment) => segment.text.length > 0);
    let marker: string | null = null;
    let heading: number | null = null;
    if (firstIndex !== -1) {
      const bullet = BULLET.exec(current[firstIndex].text);
      const hash = bullet ? null : HEADING.exec(current[firstIndex].text);
      const match = bullet ?? hash;
      if (match) {
        marker = bullet ? match[1] : null;
        heading = hash ? hash[1].length : null;
        const trimmed = current[firstIndex].text.slice(match[0].length);
        current = current.map((segment, index) =>
          index === firstIndex ? { ...segment, text: trimmed } : segment,
        );
      }
    }
    lines.push({ marker, heading, segments: current });
  };

  for (const segment of segments) {
    if (segment.lineBreak) {
      flush();
      current = [];
      continue;
    }
    current.push(segment);
  }
  flush();
  return lines;
}

function lineText(line: MarkdownLine): string {
  return line.segments.map((segment) => segment.text).join("");
}

function isTableRow(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.startsWith("|") && trimmed.endsWith("|") && trimmed.split("|").length >= 3;
}

function isTableSeparator(text: string): boolean {
  return /^\|[\s:|-]+\|$/.test(text.trim());
}

function splitRow(text: string): string[] {
  return text.trim().slice(1, -1).split("|").map((cell) => cell.trim());
}

type MarkdownBlock =
  | { kind: "line"; line: MarkdownLine }
  | { kind: "table"; header: string[]; rows: string[][] };

/**
 * Lifts pipe tables out of the line stream so the model's tables render as real
 * tables instead of rows of "| a | b |" text.
 */
function toBlocks(lines: MarkdownLine[]): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const header = lineText(lines[index]);
    const next = index + 1 < lines.length ? lineText(lines[index + 1]) : "";
    if (isTableRow(header) && isTableSeparator(next)) {
      const rows: string[][] = [];
      let cursor = index + 2;
      while (cursor < lines.length && isTableRow(lineText(lines[cursor]))) {
        rows.push(splitRow(lineText(lines[cursor])));
        cursor += 1;
      }
      blocks.push({ kind: "table", header: splitRow(header), rows });
      index = cursor;
      continue;
    }
    blocks.push({ kind: "line", line: lines[index] });
    index += 1;
  }

  return blocks;
}

/** A real bordered table, matching the dark surfaces used elsewhere. */
export function MarkdownTable({ header, rows }: { header: string[]; rows: string[][] }) {
  return (
    <span className="my-2 block overflow-x-auto rounded-lg border border-neutral-800">
      <table className="w-full border-collapse text-left text-[12.5px]">
        <thead>
          <tr className="bg-neutral-900/70">
            {header.map((cell, index) => (
              <th
                key={index}
                scope="col"
                className="border-b border-r border-neutral-800 px-3 py-2 font-medium text-neutral-100 last:border-r-0"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="border-b border-r border-neutral-800 px-3 py-2 text-neutral-300 last:border-r-0"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </span>
  );
}

/** Renders a single line of model text with inline markdown resolved. */
export function MarkdownInline({ text, className }: { text: string; className?: string }) {
  const segments = toSegments([{ text }]);
  return (
    <span className={className}>
      {segments.map((segment, index) => segmentNode(segment, index, [], false))}
    </span>
  );
}

function usePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(mediaQuery.matches);
    update();
    mediaQuery.addEventListener("change", update);
    return () => mediaQuery.removeEventListener("change", update);
  }, []);

  return reducedMotion;
}

function sourceImage(source: StreamingSource) {
  return source.image ?? SOURCE_IMAGES.scoop;
}

function Caret({ reducedMotion }: { reducedMotion: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="ml-0.5 inline-block h-3 w-0.5 translate-y-0.5 rounded-full bg-neutral-300"
      style={reducedMotion ? undefined : { animation: "fade-in 150ms ease-out both" }}
    />
  );
}

function segmentNode(
  segment: Segment,
  index: number,
  sources: StreamingSource[],
  reducedMotion: boolean,
) {
  if (segment.cite) return <SourceChip key={`cite-${index}`} source={sources[0]} />;
  if (!segment.text) return null;
  return (
    <span
      key={`segment-${index}`}
      className={cn(
        "inline",
        segment.bold && "font-semibold text-neutral-100",
        segment.code && "rounded bg-neutral-800 px-1 font-mono text-[12.5px] text-neutral-100",
      )}
      style={
        reducedMotion || !segment.text.trim()
          ? undefined
          : { animation: "stream-word-in 280ms ease-out both" }
      }
    >
      {segment.text}
    </span>
  );
}

function SourceChip({ source }: { source: StreamingSource }) {
  return (
    <a
      href={source.href}
      target="_blank"
      rel="noreferrer"
      className="mx-1 inline-flex h-[18px] translate-y-[-1px] items-center gap-1 rounded-[5px] border border-white/10 bg-neutral-900 px-1.5 align-middle font-mono text-[10.5px] text-neutral-400 shadow-sm transition-colors duration-150 hover:bg-neutral-800 hover:text-neutral-100"
    >
      <img src={sourceImage(source)} alt="" className="size-3 rounded-[3px]" />
      <span>{source.domain}</span>
    </a>
  );
}

function useCopyFeedback() {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const markCopied = () => {
    setCopied(true);
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    timeoutRef.current = window.setTimeout(() => setCopied(false), 1800);
  };

  return { copied, markCopied };
}

export function StreamingText({
  text = DEFAULT_TEXT,
  sources = DEFAULT_STREAMING_SOURCES,
  followUps = DEFAULT_FOLLOW_UPS,
  isStreaming = true,
  speed = 80,
  mode = "simulated",
  format = "plain",
  className,
  onComplete,
  onFollowUp,
  onRetry,
  ...props
}: StreamingTextProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [count, setCount] = useState(0);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const { copied, markCopied } = useCopyFeedback();
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const tokens = useMemo(() => {
    const parts = text.split(/(\s+)/).filter(Boolean);
    const firstSentenceEnd = parts.findIndex((part) => /[.!?]$/.test(part));
    const sourceIndex =
      sources.length > 0
        ? Math.max(1, firstSentenceEnd >= 0 ? firstSentenceEnd + 1 : Math.floor(parts.length / 2))
        : -1;

    return parts.flatMap((part, index) => [
      { text: part },
      ...(index === sourceIndex ? [{ text: "", cite: true }] : []),
    ]);
  }, [sources.length, text]);

  const isLive = mode === "live";
  const rendered = isLive ? tokens.length : count;
  const done = rendered >= tokens.length && (isLive ? !isStreaming : true);

  useEffect(() => {
    setSourcesOpen(false);
    let completed = false;

    const complete = () => {
      if (completed) return;
      completed = true;
      onCompleteRef.current?.();
    };

    if (isLive) {
      // Live text is already the source of truth; never retype it.
      setCount(tokens.length);
      return;
    }

    if (!isStreaming || reducedMotion) {
      setCount(tokens.length);
      complete();
      return;
    }

    setCount(0);
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setCount(index);
      if (index >= tokens.length) {
        window.clearInterval(timer);
        complete();
      }
    }, Math.max(20, speed));

    return () => window.clearInterval(timer);
  }, [isLive, isStreaming, reducedMotion, speed, text, tokens.length]);

  useEffect(() => {
    if (!isLive || isStreaming) return;
    onCompleteRef.current?.();
  }, [isLive, isStreaming]);

  const handleCopy = async () => {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(text);
      markCopied();
    } catch {
      return;
    }
  };

  return (
    <div
      className={cn("w-full max-w-[38rem] select-text", className)}
      {...props}
    >
      <div
        aria-live="polite"
        aria-atomic="false"
        className="text-[13.5px] leading-relaxed text-neutral-200"
      >
        {format === "markdown" ? (
          (() => {
            const blocks = toBlocks(toLines(toSegments(tokens.slice(0, rendered))));
            return blocks.map((block, blockIndex) => {
              const isLastBlock = blockIndex === blocks.length - 1;

              if (block.kind === "table") {
                return (
                  <MarkdownTable key={`table-${blockIndex}`} header={block.header} rows={block.rows} />
                );
              }

              const { line } = block;
              return (
                <span
                  key={`line-${blockIndex}`}
                  className={cn(
                    line.marker
                      ? "flex items-baseline gap-2"
                      : line.segments.length === 0
                        ? "block h-3"
                        : "block",
                    line.heading !== null && "mt-1 font-semibold text-neutral-100",
                    line.heading === 1 && "text-[15px]",
                    line.heading === 2 && "text-[14px]",
                  )}
                >
                  {line.marker && (
                    <span className="w-4 flex-shrink-0 text-right text-neutral-500">
                      {line.marker}
                    </span>
                  )}
                  <span className={line.marker ? "min-w-0 flex-1" : undefined}>
                    {line.segments.map((segment, index) =>
                      segmentNode(segment, index, sources, Boolean(reducedMotion)),
                    )}
                    {isLastBlock && !done && <Caret reducedMotion={Boolean(reducedMotion)} />}
                  </span>
                </span>
              );
            });
          })()
        ) : (
          <>
            {tokens.slice(0, rendered).map((token, index) =>
              token.cite ? (
                <SourceChip key={`source-${index}`} source={sources[0]} />
              ) : token.text.trim() ? (
                <span
                  key={`${token.text}-${index}`}
                  className="inline"
                  style={
                    reducedMotion
                      ? undefined
                      : { animation: "stream-word-in 280ms ease-out both" }
                  }
                >
                  {token.text}
                </span>
              ) : (
                <span key={`${token.text}-${index}`}>{token.text}</span>
              ),
            )}
            {!done && <Caret reducedMotion={Boolean(reducedMotion)} />}
          </>
        )}
      </div>

      <div
        className="mt-2 flex items-center gap-0.5 transition-opacity duration-300"
        style={{ opacity: done ? 1 : 0, pointerEvents: done ? "auto" : "none" }}
      >
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? "Respons disalin" : "Salin respons"}
          className="flex size-6 items-center justify-center rounded-[6px] text-neutral-500 transition-colors duration-100 hover:bg-neutral-800 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
        >
          {copied ? (
            <CheckCheck className="size-3.5 text-emerald-400" aria-hidden="true" />
          ) : (
            <Copy className="size-3.5" aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          onClick={onRetry}
          aria-label="Ulangi respons"
          className="flex size-6 items-center justify-center rounded-[6px] text-neutral-500 transition-colors duration-100 hover:bg-neutral-800 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Respons membantu"
          className="flex size-6 items-center justify-center rounded-[6px] text-neutral-500 transition-colors duration-100 hover:bg-neutral-800 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
        >
          <ThumbsUp className="size-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Respons tidak membantu"
          className="flex size-6 items-center justify-center rounded-[6px] text-neutral-500 transition-colors duration-100 hover:bg-neutral-800 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
        >
          <ThumbsDown className="size-3.5" aria-hidden="true" />
        </button>

        {sources.length > 0 && (
          <button
            type="button"
            aria-expanded={sourcesOpen}
            onClick={() => setSourcesOpen((current) => !current)}
            className="ml-1.5 flex items-center gap-1.5 rounded-[6px] px-1 py-0.5 text-left transition-colors duration-150 hover:bg-neutral-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
          >
            <span className="flex -space-x-1">
              {sources.map((source) => (
                <img
                  key={source.domain}
                  src={sourceImage(source)}
                  alt=""
                  className="size-3.5 rounded-full bg-neutral-950 shadow-[0_0_0_1.5px_#050505]"
                />
              ))}
            </span>
            <span className="text-[12px] text-neutral-400">
              {sources.length} {sources.length === 1 ? "sumber" : "sumber"}
            </span>
            <ChevronDown
              className={cn(
                "size-3 text-neutral-500 transition-transform duration-200",
                sourcesOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
        )}
      </div>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-300"
        style={{
          gridTemplateRows: done && sourcesOpen ? "1fr" : "0fr",
          opacity: done && sourcesOpen ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="overflow-hidden">
          <div className="mt-1.5 flex flex-col rounded-lg border border-white/10 bg-neutral-900/80 p-1 shadow-sm">
            {sources.map((source) => (
              <a
                key={source.domain}
                href={source.href}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 rounded-[6px] px-1.5 py-1 text-[12px] text-neutral-400 transition-colors duration-150 hover:bg-neutral-800 hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
              >
                <img
                  src={sourceImage(source)}
                  alt=""
                  className="size-4 rounded-[4px]"
                />
                <span>{source.name}</span>
                <span className="ml-auto font-mono text-[10.5px] text-neutral-600">
                  {source.domain}
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>

      {followUps.length > 0 && (
        <div
          className="mt-2.5 transition-opacity duration-300"
          style={{ opacity: done ? 1 : 0, pointerEvents: done ? "auto" : "none" }}
        >
          <p className="text-[12px] font-medium text-neutral-400">Tindak lanjut</p>
          <div className="mt-0.5 flex flex-col">
            {followUps.map((followUp, index) => (
              <button
                key={followUp}
                type="button"
                onClick={() => onFollowUp?.(followUp)}
                className="-mx-1.5 flex items-center gap-2 border-b border-white/10 px-1.5 py-1.5 text-left text-[12.5px] text-neutral-200 transition-colors duration-100 hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
                style={
                  done && !reducedMotion
                    ? {
                        animation: `fade-up 350ms cubic-bezier(0.23,1,0.32,1) ${index * 90}ms both`,
                      }
                    : undefined
                }
              >
                <RotateCcw className="size-3 shrink-0 rotate-[-40deg] text-neutral-500" aria-hidden="true" />
                {followUp}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

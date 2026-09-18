"use client";

import {
  File,
  FileArchive,
  FileAudio,
  FileCode2,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Folder,
} from "lucide-react";

import type { FileEntry, FileListing, ToolEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

const TEXT_EXT = new Set([".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"]);
const SHEET_EXT = new Set([".xls", ".xlsx", ".csv", ".ods"]);
const IMAGE_EXT = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff"]);
const VIDEO_EXT = new Set([".mp4", ".mov", ".avi", ".mkv", ".webm"]);
const AUDIO_EXT = new Set([".mp3", ".wav", ".m4a", ".ogg", ".flac"]);
const ARCHIVE_EXT = new Set([".zip", ".rar", ".7z", ".tar", ".gz"]);
const CODE_EXT = new Set([
  ".js", ".ts", ".tsx", ".jsx", ".py", ".json", ".html", ".css", ".sh", ".sql", ".yml", ".yaml",
]);

/** Files shown before the list is summarised, so a huge folder stays readable. */
const VISIBLE_FILE_LIMIT = 20;

function iconFor(extension: string) {
  const ext = extension.toLowerCase();
  if (TEXT_EXT.has(ext)) return FileText;
  if (SHEET_EXT.has(ext)) return FileSpreadsheet;
  if (IMAGE_EXT.has(ext)) return FileImage;
  if (VIDEO_EXT.has(ext)) return FileVideo;
  if (AUDIO_EXT.has(ext)) return FileAudio;
  if (ARCHIVE_EXT.has(ext)) return FileArchive;
  if (CODE_EXT.has(ext)) return FileCode2;
  return File;
}

export function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${(kb < 10 ? kb.toFixed(1) : Math.round(kb)).toString().replace(".", ",")} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${(mb < 10 ? mb.toFixed(1) : Math.round(mb)).toString().replace(".", ",")} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(1).replace(".", ",")} GB`;
}

function lastSegment(directory: string): string {
  const parts = directory.split(/[\\/]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : directory;
}

function isEntry(value: unknown): value is FileEntry {
  return Boolean(value) && typeof value === "object" && typeof (value as FileEntry).name === "string";
}

/**
 * Reads a folder listing out of the tools that produce one. The worker stores
 * tool output verbatim, so this renders the same data the agent saw.
 */
export function parseFileListing(
  toolEvents: ToolEvent[],
  toolResult?: unknown,
): FileListing | null {
  const candidates: unknown[] = [];
  if (toolResult) candidates.push(toolResult);
  for (const event of toolEvents) {
    if (event.result) candidates.push(event.result);
  }

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    const value = candidate as {
      directory?: unknown;
      folders?: unknown;
      files?: unknown;
      results?: unknown;
      file_count?: unknown;
      count?: unknown;
      truncated?: unknown;
      query?: unknown;
    };

    const fileSource = Array.isArray(value.files)
      ? value.files
      : Array.isArray(value.results)
        ? value.results
        : null;
    if (!fileSource) continue;

    const files = fileSource.filter(isEntry);
    const folders = Array.isArray(value.folders)
      ? value.folders.filter((folder): folder is string => typeof folder === "string")
      : [];
    const directory =
      typeof value.directory === "string" ? value.directory : "";
    if (files.length === 0 && folders.length === 0) continue;

    return {
      directory,
      files,
      folders,
      fileCount:
        typeof value.file_count === "number"
          ? value.file_count
          : typeof value.count === "number"
            ? value.count
            : files.length,
      truncated: Boolean(value.truncated) || fileSource.length > files.length,
      query: typeof value.query === "string" && value.query ? value.query : undefined,
    };
  }

  return null;
}

export function FileListCard({
  listing,
  className,
}: {
  listing: FileListing;
  className?: string;
}) {
  const visibleFiles = listing.files.slice(0, VISIBLE_FILE_LIMIT);
  const hiddenFiles = listing.files.length - visibleFiles.length;
  const title = listing.query
    ? `Hasil pencarian "${listing.query}"`
    : lastSegment(listing.directory) || "Folder";

  return (
    <div
      className={cn(
        "w-full max-w-[38rem] overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900/50",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-4 border-b border-neutral-800 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <Folder className="h-4 w-4 flex-shrink-0 text-violet-300" aria-hidden="true" />
          <span className="truncate text-sm font-medium text-neutral-100">{title}</span>
        </div>
        <span className="flex-shrink-0 text-xs tabular-nums text-neutral-500">
          {listing.fileCount} file
          {listing.folders.length > 0 ? ` · ${listing.folders.length} folder` : ""}
        </span>
      </div>

      {listing.folders.length > 0 && (
        <ul className="divide-y divide-neutral-800">
          {listing.folders.map((folder) => (
            <li key={folder} className="flex items-center gap-3 px-5 py-2.5">
              <Folder className="h-3.5 w-3.5 flex-shrink-0 text-amber-300" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-neutral-200">{folder}</span>
              <span className="flex-shrink-0 text-[11px] text-neutral-600">folder</span>
            </li>
          ))}
        </ul>
      )}

      {visibleFiles.length > 0 && (
        <ul
          className={cn(
            "divide-y divide-neutral-800",
            listing.folders.length > 0 && "border-t border-neutral-800",
          )}
        >
          {visibleFiles.map((file, index) => {
            const Icon = iconFor(file.extension);
            return (
              <li key={`${file.name}-${index}`} className="flex items-center gap-3 px-5 py-2.5">
                <Icon className="h-3.5 w-3.5 flex-shrink-0 text-neutral-500" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-[13px] text-neutral-200">{file.name}</span>
                <span className="flex-shrink-0 font-mono text-[11px] tabular-nums text-neutral-600">
                  {formatSize(file.size)}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {(hiddenFiles > 0 || listing.truncated) && (
        <p className="border-t border-neutral-800 px-5 py-3 text-xs text-neutral-600">
          {hiddenFiles > 0
            ? `+${hiddenFiles} file lain tidak ditampilkan.`
            : "Daftar dipotong di batas pemindaian."}
        </p>
      )}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Bell, CheckCircle2, Info, TriangleAlert } from "lucide-react";

import { apiGet, apiPost } from "@/lib/api";
import type { Notification, SupervisorNotifications } from "@/lib/types";
import { cn } from "@/lib/utils";

const POLL_MS = 15000;

const TONES: Record<Notification["type"], { Icon: typeof Info; className: string }> = {
  success: { Icon: CheckCircle2, className: "text-emerald-300" },
  error: { Icon: AlertTriangle, className: "text-red-300" },
  warning: { Icon: TriangleAlert, className: "text-amber-300" },
  info: { Icon: Info, className: "text-violet-300" },
};

function timeAgo(iso: string): string {
  const elapsed = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(elapsed)) return "—";
  const minutes = Math.max(0, Math.round(elapsed / 60000));
  if (minutes < 1) return "Baru saja";
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  return new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short" });
}

/** Polls the notification feed; the API has no push channel. */
export function useNotifications(scope: "user" | "supervisor") {
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);

  const load = useCallback(() => {
    if (scope === "user") {
      Promise.all([
        apiGet<Notification[]>("/user/notifications"),
        apiGet<{ count: number }>("/user/notifications/unread-count"),
      ])
        .then(([list, count]) => {
          setItems(list);
          setUnread(count.count);
        })
        .catch(() => undefined);
      return;
    }
    apiGet<SupervisorNotifications>("/supervisor/notifications")
      .then((data) => {
        setItems(data.items);
        setUnread(data.unread);
      })
      .catch(() => undefined);
  }, [scope]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const markRead = useCallback(
    (id: number) => {
      const path =
        scope === "user"
          ? `/user/notifications/${id}/read`
          : `/supervisor/notifications/${id}/read`;
      apiPost(path)
        .then(load)
        .catch(() => undefined);
    },
    [load, scope],
  );

  return { items, unread, reload: load, markRead };
}

export function NotificationRows({
  items,
  onRead,
  className,
}: {
  items: Notification[];
  onRead: (id: number) => void;
  className?: string;
}) {
  if (items.length === 0) {
    return <p className={cn("px-5 py-6 text-sm text-neutral-500", className)}>Belum ada notifikasi.</p>;
  }

  return (
    <ul className={className}>
      {items.map((item) => {
        const { Icon, className: tone } = TONES[item.type] ?? TONES.info;
        const unread = item.is_read === 0;
        return (
          <li key={item.id} className="border-b border-neutral-800 last:border-b-0">
            <button
              type="button"
              onClick={() => {
                if (unread) onRead(item.id);
              }}
              className="flex w-full items-start gap-3 px-5 py-4 text-left transition-colors hover:bg-neutral-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50"
            >
              <Icon className={cn("mt-0.5 h-4 w-4 flex-shrink-0", tone)} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "min-w-0 truncate text-sm",
                      unread ? "font-medium text-neutral-100" : "text-neutral-300",
                    )}
                  >
                    {item.title}
                  </span>
                  {unread && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-violet-300" aria-hidden="true" />
                  )}
                </span>
                {item.body && (
                  <span className="mt-0.5 block text-[13px] leading-6 text-neutral-500">{item.body}</span>
                )}
                <span className="mt-1 block text-[11px] text-neutral-600">{timeAgo(item.created_at)}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function NotificationBell({
  items,
  unread,
  onRead,
  className,
}: {
  items: Notification[];
  unread: number;
  onRead: (id: number) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <button
        type="button"
        aria-label={unread > 0 ? `Notifikasi, ${unread} belum dibaca` : "Notifikasi"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-neutral-700 bg-neutral-950 text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.98]"
      >
        <Bell className="h-4 w-4" aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-violet-400 px-1 text-[10px] font-medium tabular-nums text-neutral-950">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[min(88vw,380px)] overflow-hidden rounded-xl border border-neutral-800 bg-[#070707] shadow-[0_18px_40px_-18px_rgba(0,0,0,0.9)]">
          <div className="flex items-center justify-between border-b border-neutral-800 px-5 py-3">
            <p className="text-sm font-medium text-neutral-100">Notifikasi</p>
            <span className="text-xs text-neutral-600">
              {unread > 0 ? `${unread} belum dibaca` : "Semua sudah dibaca"}
            </span>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            <NotificationRows items={items} onRead={onRead} />
          </div>
        </div>
      )}
    </div>
  );
}

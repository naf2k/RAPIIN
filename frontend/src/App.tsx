import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import {
  CircleUserRound,
  Settings,
  SquarePen,
  Trash2,
} from "lucide-react";

import { RapiinLogo } from "@/components/ui/rapiin-logo";
import RuixenMoonChat from "@/components/ui/ruixen-moon-chat";
import {
  Sidebar,
  SidebarBody,
  SidebarLink,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { useSessionToken, useSessionUser } from "@/lib/session";
import {
  deleteConversation,
  listSessions,
  loadMessages,
  timeLabel,
  type ChatSessionMeta,
} from "@/lib/chat-store";
import { ApiError } from "@/lib/api";
import type { Message } from "@/lib/types";
import { UserAccountPage, UserSettingsPage } from "@/src/user/UserSettingsPage";

const SupervisorApp = lazy(() => import("@/src/supervisor/SupervisorApp"));
const LoginPage = lazy(() => import("@/src/auth/LoginPage"));
const OnboardingPage = lazy(() => import("@/src/user/OnboardingPage"));

function useRedirect(target: string | null) {
  useEffect(() => {
    if (target) window.location.replace(target);
  }, [target]);
}

export default function App() {
  const path = window.location.pathname;
  const token = useSessionToken();
  const user = useSessionUser();

  const isLoginRoute = path.startsWith("/login");
  const wantsSupervisor = path.startsWith("/supervisor");

  // Routing stays pathname-based, exactly as before. This only decides whether
  // the visitor is allowed to see the route they asked for.
  let redirectTo: string | null = null;
  if (!token) {
    // Onboarding registers a device for the signed-in account, so it needs a session.
    if (!isLoginRoute) redirectTo = "/login";
  } else if (user?.role === "SUPERVISOR" && !wantsSupervisor) {
    redirectTo = "/supervisor";
  } else if (user?.role === "USER" && wantsSupervisor) {
    redirectTo = "/";
  }

  useRedirect(redirectTo);

  if (redirectTo) return <RouteLoading label="Mengalihkan..." />;

  if (path.startsWith("/login")) {
    return (
      <Suspense fallback={<RouteLoading label="Memuat halaman login..." />}>
        <LoginPage />
      </Suspense>
    );
  }

  if (path.startsWith("/onboarding")) {
    return (
      <Suspense fallback={<RouteLoading label="Memuat setup..." />}>
        <OnboardingPage />
      </Suspense>
    );
  }

  if (wantsSupervisor) {
    return (
      <Suspense fallback={<RouteLoading label="Memuat supervisor workspace..." />}>
        <SupervisorApp />
      </Suspense>
    );
  }

  return <UserApp />;
}

function RouteLoading({ label }: { label: string }) {
  return (
    <div className="dark flex h-[100dvh] items-center justify-center bg-[#050505] text-neutral-500">
      <div className="flex items-center gap-3 text-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-violet-300" />
        {label}
      </div>
    </div>
  );
}

type ChatView = { kind: "live" } | { kind: "history"; id: number };

function UserApp() {
  const [open, setOpen] = useState(false);
  const [route, setRoute] = useState(() => window.location.pathname);
  const [view, setView] = useState<ChatView>({ kind: "live" });
  const [liveKey, setLiveKey] = useState(0);
  const [liveConversationId, setLiveConversationId] = useState<number | null>(null);
  const [historyMessages, setHistoryMessages] = useState<Message[] | null>(null);
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);

  useEffect(() => {
    const handlePopState = () => setRoute(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const refreshSessions = useCallback(() => {
    listSessions()
      .then(setSessions)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const closeMobileSidebar = () => {
    if (window.matchMedia("(max-width: 767px)").matches) setOpen(false);
  };

  const navigate = (path: string) => {
    if (window.location.pathname !== path) window.history.pushState({}, "", path);
    setRoute(path);
    closeMobileSidebar();
  };

  const handleNewChat = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    goHome();
  };

  const goHome = () => {
    navigate("/");
    setView({ kind: "live" });
    setLiveConversationId(null);
    setHistoryMessages(null);
    setLiveKey((current) => current + 1);
  };

  const handleOpenHistory = (event: MouseEvent<HTMLButtonElement>, id: number) => {
    event.preventDefault();
    navigate("/");
    setView({ kind: "history", id });
    setHistoryMessages(null);
    loadMessages(id)
      .then(setHistoryMessages)
      .catch(() => setHistoryMessages([]));
  };

  const handleDeleteHistory = (event: MouseEvent<HTMLButtonElement>, id: number) => {
    event.preventDefault();
    event.stopPropagation();
    deleteConversation(id)
      .then(() => {
        refreshSessions();
        const wasOpen =
          (view.kind === "history" && view.id === id) ||
          (view.kind === "live" && liveConversationId === id);
        if (!wasOpen) return;
        // The open chat is gone; start a fresh one instead of showing a ghost.
        setView({ kind: "live" });
        setLiveConversationId(null);
        setLiveKey((key) => key + 1);
      })
      .catch((cause: unknown) => {
        // A conversation that is still being processed refuses to delete.
        window.alert(
          cause instanceof ApiError ? cause.message : "Percakapan tidak dapat dihapus.",
        );
      });
  };

  const activeSessionId = view.kind === "history" ? view.id : liveConversationId;
  const userView = route.startsWith("/settings")
    ? "settings"
    : route.startsWith("/account")
      ? "account"
      : "chat";

  return (
    <main className="dark h-[100dvh] w-full overflow-hidden bg-neutral-950 text-white">
      <div
        className={cn(
          "mx-auto flex h-full min-h-0 w-full flex-col overflow-hidden rounded-md border border-neutral-800 bg-neutral-950 md:flex-row",
        )}
      >
        <Sidebar open={open} setOpen={setOpen}>
          <SidebarBody className="h-full min-h-0 justify-between gap-8">
            <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
              <Logo onNavigateHome={goHome} />
              <div className="mt-8 flex flex-col gap-1">
                <SidebarLink
                  link={{
                    label: "Chat Baru",
                    href: "#new-chat",
                    icon: <SquarePen className="h-5 w-5 flex-shrink-0 text-neutral-300" strokeWidth={1.8} />,
                  }}
                  onClick={handleNewChat}
                  className="w-full rounded-lg transition-colors duration-150 hover:bg-neutral-900"
                />
              </div>

              <div className="mt-7 flex flex-col gap-1">
                <SidebarSectionLabel>Chat Terakhir</SidebarSectionLabel>
                {sessions.length === 0 ? (
                  <EmptyHistoryNotice />
                ) : (
                  sessions.map((session) => (
                    <HistoryLink
                      key={session.id}
                      title={session.title}
                      meta={`${session.turnCount} pesan · ${timeLabel(session.updatedAt)}`}
                      active={activeSessionId === session.id}
                      onOpen={(event) => handleOpenHistory(event, session.id)}
                      onDelete={(event) => handleDeleteHistory(event, session.id)}
                    />
                  ))
                )}
              </div>
            </div>

            <div className="mt-auto flex flex-col gap-1 border-t border-neutral-800 pt-4">
              <SidebarLink
                link={{
                  label: "Pengaturan",
                  href: "/settings",
                  icon: <Settings className="h-5 w-5 flex-shrink-0 text-neutral-400" />,
                }}
                onClick={(event) => {
                  event.preventDefault();
                  navigate("/settings");
                }}
                className="w-full rounded-lg transition-colors duration-150 hover:bg-neutral-900"
              />
              <SidebarLink
                link={{
                  label: "Akun",
                  href: "/account",
                  icon: <CircleUserRound className="h-5 w-5 flex-shrink-0 text-neutral-400" />,
                }}
                onClick={(event) => {
                  event.preventDefault();
                  navigate("/account");
                }}
                className="w-full rounded-lg transition-colors duration-150 hover:bg-neutral-900"
              />
            </div>
          </SidebarBody>
        </Sidebar>
        <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
          {userView === "settings" ? (
            <UserSettingsPage />
          ) : userView === "account" ? (
            <UserAccountPage />
          ) : view.kind === "history" ? (
            historyMessages === null ? (
              <RouteLoading label="Memuat percakapan..." />
            ) : (
              <RuixenMoonChat
                key={`history-${view.id}`}
                conversationId={view.id}
                initialMessages={historyMessages}
                onTurnSettled={refreshSessions}
              />
            )
          ) : (
            <RuixenMoonChat
              key={`live-${liveKey}`}
              conversationId={liveConversationId}
              onConversationChange={(id) => {
                setLiveConversationId(id);
                refreshSessions();
              }}
              onTurnSettled={refreshSessions}
            />
          )}
        </div>
      </div>
    </main>
  );
}

function SidebarSectionLabel({ children }: { children: ReactNode }) {
  const { open, animate } = useSidebar();
  const labelVisible = !animate || open;

  return (
    <span
      aria-hidden={animate && !open}
      className={cn(
        "mb-1 whitespace-pre text-[11px] font-medium uppercase tracking-[0.12em] text-neutral-600 transition-[opacity,transform] ease-[cubic-bezier(0.23,1,0.32,1)]",
        labelVisible
          ? "translate-x-0 opacity-100 delay-75 duration-200"
          : "pointer-events-none -translate-x-1.5 opacity-0 delay-0 duration-100",
      )}
    >
      {children}
    </span>
  );
}

function EmptyHistoryNotice() {
  const { open, animate } = useSidebar();
  const labelVisible = !animate || open;

  return (
    <span
      aria-hidden={animate && !open}
      className={cn(
        "whitespace-pre px-2 py-2 text-xs text-neutral-600 transition-[opacity,transform] ease-[cubic-bezier(0.23,1,0.32,1)]",
        labelVisible
          ? "translate-x-0 opacity-100 delay-75 duration-200"
          : "pointer-events-none -translate-x-1.5 opacity-0 delay-0 duration-100",
      )}
    >
      Belum ada riwayat chat.
    </span>
  );
}

function HistoryLink({
  title,
  meta,
  active,
  onOpen,
  onDelete,
}: {
  title: string;
  meta: string;
  active: boolean;
  onOpen: (event: MouseEvent<HTMLButtonElement>) => void;
  onDelete: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  const { open, animate } = useSidebar();
  const labelVisible = !animate || open;

  return (
    <div
      className={cn(
        "group/history flex items-center gap-1 rounded-lg transition-colors duration-150 hover:bg-neutral-900",
        active && labelVisible && "bg-neutral-900",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Buka ${title}`}
        aria-current={active ? true : undefined}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg py-2 pl-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
      >
        <span
          aria-hidden={animate && !open}
          className={cn(
            "inline-block min-w-0 flex-1 whitespace-pre text-sm text-neutral-300 transition-[opacity,transform] ease-[cubic-bezier(0.23,1,0.32,1)] !m-0 !p-0",
            labelVisible
              ? "translate-x-0 opacity-100 delay-75 duration-200"
              : "pointer-events-none -translate-x-1.5 opacity-0 delay-0 duration-100",
          )}
        >
          <span className="block truncate">{title}</span>
          <span className="mt-0.5 block truncate text-[11px] text-neutral-600">{meta}</span>
        </span>
      </button>
      {labelVisible && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={`Hapus ${title}`}
          className="mr-1 inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-neutral-600 opacity-0 transition-[opacity,color,background-color] hover:bg-neutral-800 hover:text-neutral-200 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 group-hover/history:opacity-100"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function Logo({ onNavigateHome }: { onNavigateHome: () => void }) {
  const { open, animate } = useSidebar();
  const labelVisible = !animate || open;

  return (
    <a
      href="/"
      onClick={(event) => {
        event.preventDefault();
        onNavigateHome();
      }}
      aria-label="RAPIIN"
      className="font-normal flex space-x-2 items-center text-sm text-white py-1 relative z-20"
    >
      <RapiinLogo className="text-neutral-100" />
      <span
        aria-hidden={animate && !open}
        className={cn(
          "whitespace-pre font-medium text-white transition-[opacity,transform] ease-[cubic-bezier(0.23,1,0.32,1)]",
          labelVisible
            ? "translate-x-0 opacity-100 delay-75 duration-200"
            : "pointer-events-none -translate-x-1.5 opacity-0 delay-0 duration-100",
        )}
      >
        RAPIIN
      </span>
    </a>
  );
}

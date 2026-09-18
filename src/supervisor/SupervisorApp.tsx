import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  CircleCheck,
  CircleUserRound,
  ClipboardList,
  Laptop,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Send,
  ServerCog,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "lucide-react";

import { BeresinLogo } from "@/components/ui/beresin-logo";
import { NotificationBell, useNotifications } from "@/components/ui/beresin-notifications";
import { Button } from "@/components/ui/button";
import { ApiError, apiPost } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  pageTitles,
  type ApprovalRequest,
  type Device,
  type Employee,
  type SupervisorPage,
  type SupervisorTask,
} from "@/src/supervisor/data";
import {
  SupervisorDataProvider,
  useSupervisorData,
} from "@/src/supervisor/live-data";
import {
  AccountPage,
  ActivityPage,
  ApprovalsPage,
  DevicesPage,
  EmployeesPage,
  OperationsPage,
  OverviewPage,
  SettingsPage,
  TasksPage,
} from "@/src/supervisor/SupervisorPages";

const navItems: Array<{
  page: Exclude<SupervisorPage, "settings" | "account">;
  label: string;
  icon: ReactNode;
}> = [
  { page: "overview", label: "Ringkasan", icon: <LayoutDashboard className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
  { page: "tasks", label: "Tugas", icon: <ClipboardList className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
  { page: "employees", label: "Pegawai", icon: <Users className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
  { page: "devices", label: "Perangkat", icon: <Laptop className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
  { page: "approvals", label: "Persetujuan", icon: <ShieldCheck className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
  { page: "activity", label: "Aktivitas", icon: <Activity className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
  { page: "operations", label: "Operasi", icon: <ServerCog className="h-[18px] w-[18px]" strokeWidth={1.8} /> },
];

function pageFromPath(): SupervisorPage {
  const page = window.location.pathname.split("/").filter(Boolean)[1] as SupervisorPage | undefined;
  return page && page in pageTitles ? page : "overview";
}

/** Display ids keep their notation ("TASK-1043"); the API needs the numeric part. */
function numericId(displayId: string): number | null {
  const digits = displayId.replace(/[^0-9]/g, "");
  if (!digits) return null;
  const value = Number(digits);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export default function SupervisorApp() {
  return (
    <SupervisorDataProvider>
      <SupervisorWorkspace />
    </SupervisorDataProvider>
  );
}

function SupervisorWorkspace() {
  const { approvals, respondApproval, loadTask, loadEmployee } = useSupervisorData();
  const notifications = useNotifications("supervisor");
  const [page, setPage] = useState<SupervisorPage>(pageFromPath);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState<SupervisorTask | null>(null);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(null);
  const reducedMotion = useReducedMotion();
  const pendingApprovals = approvals.filter((approval) => approval.status === "Pending").length;

  useEffect(() => {
    const handlePopState = () => {
      setPage(pageFromPath());
      setSelectedTask(null);
      setSelectedEmployee(null);
      setSelectedDevice(null);
      setSelectedApproval(null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMobileNavOpen(false);
      setChatOpen(false);
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  const navigate = (nextPage: SupervisorPage) => {
    setPage(nextPage);
    setSelectedTask(null);
    setSelectedEmployee(null);
    setSelectedDevice(null);
    setSelectedApproval(null);
    setMobileNavOpen(false);
    const path = nextPage === "overview" ? "/supervisor" : `/supervisor/${nextPage}`;
    if (window.location.pathname !== path) window.history.pushState({}, "", path);
  };

  const openTask = (task: SupervisorTask) => {
    setPage("tasks");
    setSelectedTask(task);
    setSelectedEmployee(null);
    setSelectedDevice(null);
    setSelectedApproval(null);
    setMobileNavOpen(false);
    if (window.location.pathname !== "/supervisor/tasks") {
      window.history.pushState({}, "", "/supervisor/tasks");
    }

    // The list endpoint carries no activity trail; the detail endpoint does.
    const taskId = numericId(task.id);
    if (taskId !== null) {
      void loadTask(taskId).then((detail) => {
        if (!detail) return;
        setSelectedTask((current) =>
          current && current.id === task.id
            ? { ...detail, user: current.user, device: current.device, title: current.title }
            : current,
        );
      });
    }
  };

  const openEmployee = (employee: Employee) => {
    setPage("employees");
    setSelectedEmployee(employee);
    setSelectedTask(null);
    setSelectedDevice(null);
    setSelectedApproval(null);
    setMobileNavOpen(false);
    if (window.location.pathname !== "/supervisor/employees") {
      window.history.pushState({}, "", "/supervisor/employees");
    }

    const userId = numericId(employee.id);
    if (userId !== null) {
      void loadEmployee(userId, employee).then((detail) => {
        if (detail) setSelectedEmployee(detail);
      });
    }
  };

  const openApproval = (approval: ApprovalRequest) => {
    setPage("approvals");
    setSelectedApproval(approval);
    setSelectedTask(null);
    setSelectedEmployee(null);
    setSelectedDevice(null);
    setMobileNavOpen(false);
    if (window.location.pathname !== "/supervisor/approvals") {
      window.history.pushState({}, "", "/supervisor/approvals");
    }
  };

  const pageContent = (() => {
    switch (page) {
      case "overview":
        return (
          <OverviewPage
            approvals={approvals}
            onNavigate={navigate}
            onTaskSelect={openTask}
            onEmployeeSelect={openEmployee}
            onApprovalSelect={openApproval}
          />
        );
      case "tasks":
        return <TasksPage selectedTask={selectedTask} onSelect={setSelectedTask} />;
      case "employees":
        return (
          <EmployeesPage
            selectedEmployee={selectedEmployee}
            onSelect={setSelectedEmployee}
            onTaskSelect={openTask}
          />
        );
      case "devices":
        return (
          <DevicesPage
            selectedDevice={selectedDevice}
            onSelect={setSelectedDevice}
            onTaskSelect={openTask}
          />
        );
      case "approvals":
        return (
          <ApprovalsPage
            approvals={approvals}
            selectedApproval={selectedApproval}
            onSelect={setSelectedApproval}
            onResolve={respondApproval}
          />
        );
      case "activity":
        return <ActivityPage />;
      case "operations":
        return <OperationsPage />;
      case "settings":
        return <SettingsPage />;
      case "account":
        return <AccountPage />;
    }
  })();

  const viewKey = `${page}-${selectedTask?.id ?? selectedEmployee?.id ?? selectedDevice?.id ?? selectedApproval?.id ?? "list"}`;

  return (
    <div className="dark flex h-[100dvh] w-full overflow-hidden bg-[#050505] text-neutral-100">
      <SupervisorSidebar
        page={page}
        pendingApprovals={pendingApprovals}
        onNavigate={navigate}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-16 flex-shrink-0 items-center justify-between gap-4 border-b border-neutral-800 bg-[#070707] px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="Buka navigasi supervisor"
              onClick={() => setMobileNavOpen(true)}
              className="inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg text-neutral-300 transition-colors hover:bg-neutral-900 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 md:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-neutral-200">Workspace supervisor</p>
              <p className="mt-0.5 hidden items-center gap-1.5 text-xs text-neutral-600 sm:flex">
                <CircleCheck className="h-3.5 w-3.5 text-emerald-400" /> Sistem sehat
              </p>
            </div>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            <NotificationBell
              items={notifications.items}
              unread={notifications.unread}
              onRead={notifications.markRead}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => setChatOpen(true)}
              className="h-9 border-neutral-700 bg-neutral-950 px-3 text-neutral-200 hover:bg-neutral-800 hover:text-white active:scale-[0.98]"
            >
              <MessageSquareText className="mr-2 h-4 w-4 text-violet-300" />
              <span className="hidden sm:inline">Tanya BERESIN</span>
              <span className="sm:hidden">Tanya</span>
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto bg-[#080808]" aria-label={`${pageTitles[page]} supervisor`}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={viewKey}
              initial={reducedMotion ? false : { opacity: 0, transform: "translate3d(0, 6px, 0)" }}
              animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, transform: "translate3d(0, -3px, 0)" }}
              transition={{ duration: reducedMotion ? 0 : 0.16, ease: [0.23, 1, 0.32, 1] }}
            >
              {pageContent}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <MobileNavigation
        open={mobileNavOpen}
        page={page}
        pendingApprovals={pendingApprovals}
        onClose={() => setMobileNavOpen(false)}
        onNavigate={navigate}
        reducedMotion={Boolean(reducedMotion)}
      />
      <SupervisorChat
        open={chatOpen}
        pendingApprovals={pendingApprovals}
        onClose={() => setChatOpen(false)}
        reducedMotion={Boolean(reducedMotion)}
      />
    </div>
  );
}

function SupervisorSidebar({
  page,
  pendingApprovals,
  onNavigate,
}: {
  page: SupervisorPage;
  pendingApprovals: number;
  onNavigate: (page: SupervisorPage) => void;
}) {
  return (
    <aside className="hidden h-full w-[68px] flex-shrink-0 flex-col border-r border-neutral-800 bg-[#070707] md:flex lg:w-[232px]">
      <div className="flex h-16 flex-shrink-0 items-center border-b border-neutral-800 px-5 lg:px-5">
        <Brand compact />
      </div>

      <nav className="flex min-h-0 flex-1 flex-col px-2 py-4 lg:px-3" aria-label="Supervisor navigation">
        <div className="space-y-1">
          {navItems.map((item) => (
            <NavigationButton
              key={item.page}
              active={page === item.page}
              icon={item.icon}
              label={item.label}
              count={item.page === "approvals" ? pendingApprovals : undefined}
              onClick={() => onNavigate(item.page)}
            />
          ))}
        </div>

        <div className="mt-auto space-y-1 border-t border-neutral-800 pt-4">
          <NavigationButton
            active={page === "settings"}
            icon={<Settings className="h-[18px] w-[18px]" strokeWidth={1.8} />}
            label="Pengaturan"
            onClick={() => onNavigate("settings")}
          />
          <NavigationButton
            active={page === "account"}
            icon={<CircleUserRound className="h-[18px] w-[18px]" strokeWidth={1.8} />}
            label="Akun Supervisor"
            onClick={() => onNavigate("account")}
          />
        </div>
      </nav>
    </aside>
  );
}

function NavigationButton({
  active,
  icon,
  label,
  count,
  expanded = false,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  count?: number;
  expanded?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "group relative flex h-11 w-full items-center gap-3 rounded-lg px-3 text-sm transition-[background-color,color,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.985]",
        active ? "bg-neutral-900 text-neutral-100" : "text-neutral-500 hover:bg-neutral-900/70 hover:text-neutral-200",
      )}
    >
      {active && <span className="absolute left-0 h-5 w-0.5 rounded-full bg-violet-300" />}
      <span className={cn("flex-shrink-0", active && "text-violet-200")}>{icon}</span>
      <span className={cn("min-w-0 flex-1 truncate text-left", expanded ? "block" : "hidden lg:block")}>{label}</span>
      {typeof count === "number" && count > 0 && (
        <span className={cn("min-w-5 items-center justify-center rounded-full bg-amber-400/10 px-1.5 py-0.5 text-[11px] font-medium text-amber-200", expanded ? "inline-flex" : "hidden lg:inline-flex")}>
          {count}
        </span>
      )}
      {typeof count === "number" && count > 0 && (
        <span className={cn("absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-amber-300 lg:hidden", expanded && "hidden")} />
      )}
    </button>
  );
}

function MobileNavigation({
  open,
  page,
  pendingApprovals,
  onClose,
  onNavigate,
  reducedMotion,
}: {
  open: boolean;
  page: SupervisorPage;
  pendingApprovals: number;
  onClose: () => void;
  onNavigate: (page: SupervisorPage) => void;
  reducedMotion: boolean;
}) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button
            type="button"
            aria-label="Tutup navigasi supervisor"
            className="fixed inset-0 z-40 bg-black/70 md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.16 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label="Navigasi supervisor"
            className="fixed inset-y-0 left-0 z-50 flex w-[min(84vw,320px)] flex-col border-r border-neutral-800 bg-[#070707] md:hidden"
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, transform: "translate3d(-100%, 0, 0)" }}
            animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, transform: "translate3d(-100%, 0, 0)" }}
            transition={{ duration: reducedMotion ? 0 : 0.22, ease: [0.32, 0.72, 0, 1] }}
          >
            <div className="flex h-16 items-center justify-between border-b border-neutral-800 px-5">
              <Brand />
              <button
                type="button"
                aria-label="Tutup navigasi"
                onClick={onClose}
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-neutral-400 transition-colors hover:bg-neutral-900 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="flex min-h-0 flex-1 flex-col px-3 py-4" aria-label="Mobile supervisor navigation">
              <div className="space-y-1">
                {navItems.map((item) => (
                  <NavigationButton
                    key={item.page}
                    active={page === item.page}
                    icon={item.icon}
                    label={item.label}
                    count={item.page === "approvals" ? pendingApprovals : undefined}
                    expanded
                    onClick={() => onNavigate(item.page)}
                  />
                ))}
              </div>
              <div className="mt-auto space-y-1 border-t border-neutral-800 pt-4">
                <NavigationButton
                  active={page === "settings"}
                  icon={<Settings className="h-[18px] w-[18px]" strokeWidth={1.8} />}
                  label="Pengaturan"
                  expanded
                  onClick={() => onNavigate("settings")}
                />
                <NavigationButton
                  active={page === "account"}
                  icon={<CircleUserRound className="h-[18px] w-[18px]" strokeWidth={1.8} />}
                  label="Akun Supervisor"
                  expanded
                  onClick={() => onNavigate("account")}
                />
              </div>
            </nav>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <BeresinLogo className="text-neutral-100" />
      <div className={cn("min-w-0", compact && "hidden lg:block")}>
        <p className="truncate text-sm font-medium tracking-tight text-neutral-100">BERESIN</p>
        <p className="mt-0.5 truncate text-[10px] font-medium uppercase tracking-[0.14em] text-neutral-600">Supervisor</p>
      </div>
    </div>
  );
}

interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  text: string;
}

function SupervisorChat({
  open,
  pendingApprovals,
  onClose,
  reducedMotion,
}: {
  open: boolean;
  pendingApprovals: number;
  onClose: () => void;
  reducedMotion: boolean;
}) {
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "assistant",
      text: "Saya bisa merangkum task, device, approval, dan aktivitas yang dapat Anda akses sebagai supervisor.",
    },
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" });
  }, [messages, reducedMotion, thinking]);

  const submitPrompt = (rawPrompt: string) => {
    const prompt = rawPrompt.trim();
    if (!prompt || thinking) return;
    const userMessage: ChatMessage = { id: Date.now(), role: "user", text: prompt };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setThinking(true);

    apiPost<{ reply: string }>("/supervisor/chat", { message: prompt })
      .then((data) => {
        setMessages((current) => [
          ...current,
          { id: Date.now() + 1, role: "assistant", text: data.reply },
        ]);
      })
      .catch((cause: unknown) => {
        setMessages((current) => [
          ...current,
          {
            id: Date.now() + 2,
            role: "assistant",
            text:
              cause instanceof ApiError
                ? cause.message
                : "Maaf, jawaban belum bisa diambil saat ini.",
          },
        ]);
      })
      .finally(() => setThinking(false));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitPrompt(input);
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button
            type="button"
            aria-label="Tutup Supervisor Chat"
            className="fixed inset-0 z-40 bg-black/70"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.16 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="supervisor-chat-title"
            className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-neutral-800 bg-[#090909] sm:w-[430px]"
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, transform: "translate3d(100%, 0, 0)" }}
            animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, transform: "translate3d(100%, 0, 0)" }}
            transition={{ duration: reducedMotion ? 0 : 0.22, ease: [0.32, 0.72, 0, 1] }}
          >
            <div className="flex h-16 flex-shrink-0 items-center justify-between border-b border-neutral-800 px-5">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-400/10 text-violet-200">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <h2 id="supervisor-chat-title" className="text-sm font-medium text-neutral-100">Tanya BERESIN</h2>
                  <p className="mt-0.5 text-xs text-neutral-600">Hanya data monitoring resmi</p>
                </div>
              </div>
              <button
                type="button"
                aria-label="Tutup chat"
                onClick={onClose}
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-neutral-900 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6" aria-live="polite">
              <div className="space-y-5">
                {messages.map((message) => (
                  <div key={message.id} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
                    <div className={cn(
                      "max-w-[88%] rounded-xl px-4 py-3 text-sm leading-6",
                      message.role === "user"
                        ? "rounded-br-sm bg-neutral-100 text-neutral-950"
                        : "rounded-bl-sm border border-neutral-800 bg-neutral-900/60 text-neutral-300",
                    )}>
                      {message.text}
                    </div>
                  </div>
                ))}
                {thinking && (
                  <div className="flex justify-start">
                    <div className="inline-flex items-center gap-2 rounded-xl rounded-bl-sm border border-neutral-800 bg-neutral-900/60 px-4 py-3 text-sm text-neutral-500">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-300" />
                      Memeriksa workspace...
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {messages.length === 1 && (
              <div className="flex flex-wrap gap-2 border-t border-neutral-800 px-5 py-4">
                {["Ada masalah apa hari ini?", "Berapa device yang offline?", "Kenapa task Dimas gagal?"].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => submitPrompt(prompt)}
                    className="rounded-full border border-neutral-800 bg-neutral-950 px-3 py-2 text-left text-xs text-neutral-500 transition-colors hover:border-neutral-700 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.98]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}

            <form onSubmit={handleSubmit} className="border-t border-neutral-800 p-4">
              <label htmlFor="supervisor-chat-input" className="sr-only">Pertanyaan untuk BERESIN</label>
              <div className="flex items-end gap-2 rounded-xl border border-neutral-700 bg-neutral-950 p-2 focus-within:border-violet-400/50 focus-within:ring-2 focus-within:ring-violet-400/10">
                <textarea
                  id="supervisor-chat-input"
                  rows={1}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder="Tanya BERESIN..."
                  className="max-h-28 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-neutral-100 outline-none placeholder:text-neutral-600"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || thinking}
                  aria-label="Kirim pertanyaan"
                  className="inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-950 transition-[background-color,transform] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-600 active:scale-[0.96]"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
              <p className="mt-2 px-1 text-xs leading-5 text-neutral-700">Chat Supervisor tidak bisa melewati policy izin.</p>
            </form>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

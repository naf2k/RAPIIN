import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CirclePlay,
  CircleX,
  Clock3,
  FileCheck2,
  Info,
  Laptop,
  LoaderCircle,
  LogOut,
  OctagonPause,
  Pause,
  Play,
  Radar,
  Search,
  ServerCog,
  ShieldCheck,
  ShieldHalf,
  Siren,
  SquareTerminal,
  Stethoscope,
  UserRound,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  type ActivityEvent,
  type ApprovalRequest,
  type ApprovalStatus,
  type Device,
  type Employee,
  type EmployeeStatus,
  type OpsAgent,
  type OpsAgentRole,
  type OpsAgentState,
  type OpsApproval,
  type OpsIncident,
  type OpsIncidentStatus,
  type OpsSeverity,
  type SupervisorPage,
  type SupervisorTask,
  type TaskStatus,
} from "@/src/supervisor/data";
import { NO_DEVICE_LABEL, useSupervisorData } from "@/src/supervisor/live-data";

const surfaceClass = "rounded-xl border border-neutral-800 bg-neutral-900/35";
const inputClass =
  "h-10 w-full rounded-lg border border-neutral-800 bg-neutral-950 px-3 text-sm text-neutral-100 outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-neutral-600 focus:border-violet-400/50 focus:ring-2 focus:ring-violet-400/10";

const TASK_STATUS_ID: Record<TaskStatus, string> = {
  Running: "Berjalan",
  Waiting: "Menunggu",
  Completed: "Selesai",
  Failed: "Gagal",
};

const EMPLOYEE_STATUS_ID: Record<EmployeeStatus, string> = {
  Online: "Online",
  Offline: "Offline",
  Warning: "Perhatian",
};

const APPROVAL_STATUS_ID: Record<ApprovalStatus, string> = {
  Pending: "Menunggu",
  Approved: "Disetujui",
  Rejected: "Ditolak",
};

interface OverviewPageProps {
  approvals: ApprovalRequest[];
  onNavigate: (page: SupervisorPage) => void;
  onTaskSelect: (task: SupervisorTask) => void;
  onEmployeeSelect: (employee: Employee) => void;
  onApprovalSelect: (approval: ApprovalRequest) => void;
}

export function OverviewPage({
  approvals,
  onNavigate,
  onTaskSelect,
  onEmployeeSelect,
  onApprovalSelect,
}: OverviewPageProps) {
  const { tasks, employees: employeeList, activity, overview } = useSupervisorData();
  const failedTask = tasks.find((task) => task.status === "Failed");
  const offlineEmployee = employeeList.find(
    (employee) => employee.status === "Offline" && employee.device !== NO_DEVICE_LABEL,
  );
  const pendingApproval = approvals.find((approval) => approval.status === "Pending");
  const runningTasks = tasks.filter((task) => task.status === "Running").length;
  const onlineDevices = employeeList.filter((employee) => employee.status === "Online").length;
  const attentionCount =
    (failedTask ? 1 : 0) + (pendingApproval ? 1 : 0) + (offlineEmployee ? 1 : 0);

  return (
    <PageFrame>
      <PageIntro
        title="Ringkasan"
        description="Kondisi sistem dan pekerjaan yang membutuhkan keputusan Anda."
        aside={<DemoLabel />}
      />

      <section aria-labelledby="attention-heading" className={cn(surfaceClass, "overflow-hidden")}>
        <div className="flex items-center justify-between border-b border-neutral-800 px-5 py-4 sm:px-6">
          <div>
            <h2 id="attention-heading" className="text-base font-medium text-neutral-100">
              Perlu Perhatian
            </h2>
            <p className="mt-1 text-sm text-neutral-500">
              {attentionCount === 0
                ? "Tidak ada yang perlu ditinjau saat ini."
                : `${attentionCount} hal perlu ditinjau saat ini.`}
            </p>
          </div>
          <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-amber-400/10 px-2 text-xs font-medium text-amber-200">
            {attentionCount}
          </span>
        </div>

        <div className="divide-y divide-neutral-800">
          {failedTask && (
            <AttentionRow
              icon={<CircleX className="h-5 w-5" />}
              tone="danger"
              title={`${failedTask.user}: ${failedTask.title} gagal`}
              detail={failedTask.error ?? "Tugas berhenti dan membutuhkan tindak lanjut."}
              action="Lihat task"
              onClick={() => onTaskSelect(failedTask)}
            />
          )}
          {pendingApproval && (
            <AttentionRow
              icon={<ShieldCheck className="h-5 w-5" />}
              tone="warning"
              title={pendingApproval.action}
              detail={`${pendingApproval.user} · ${pendingApproval.risk}`}
              action="Tinjau"
              onClick={() => onApprovalSelect(pendingApproval)}
            />
          )}
          {offlineEmployee && (
            <AttentionRow
              icon={<WifiOff className="h-5 w-5" />}
              tone="warning"
              title={`${offlineEmployee.device} offline`}
              detail={`Heartbeat terakhir ${offlineEmployee.lastSeen}.`}
              action="Lihat pegawai"
              onClick={() => onEmployeeSelect(offlineEmployee)}
            />
          )}
          {attentionCount === 0 && (
            <p className="px-5 py-6 text-sm text-neutral-500 sm:px-6">
              Sistem berjalan normal. Tidak ada tindakan yang menunggu.
            </p>
          )}
        </div>
      </section>

      <section aria-labelledby="metrics-heading">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 id="metrics-heading" className="text-base font-medium text-neutral-100">
              Ringkasan Sistem
            </h2>
            <p className="mt-1 text-sm text-neutral-500">Ringkasan operasional hari ini.</p>
          </div>
          <span className="hidden text-xs text-neutral-600 sm:block">Diperbarui baru saja</span>
        </div>
        <div className={cn(surfaceClass, "grid grid-cols-2 overflow-hidden [&>*:nth-child(n+3)]:border-t lg:grid-cols-4 lg:[&>*:nth-child(n+3)]:border-t-0")}>
          <Metric
            label="Pengguna aktif"
            value={overview ? String(overview.active_users) : "—"}
            detail={`${onlineDevices} device online`}
          />
          <Metric
            label="Tugas berjalan"
            value={overview ? String(overview.running_tasks) : String(runningTasks)}
            detail={`${overview?.waiting_approvals ?? 0} menunggu persetujuan`}
          />
          <Metric
            label="Tingkat sukses"
            value={
              overview?.success_rate === null || overview?.success_rate === undefined
                ? "—"
                : `${overview.success_rate}%`
            }
            detail="Seluruh riwayat tugas"
          />
          <Metric
            label="Status sistem"
            value={overview?.status === "PERLU_PERHATIAN" ? "Perlu perhatian" : "Sehat"}
            detail={
              overview?.status === "PERLU_PERHATIAN"
                ? "Ada tugas yang gagal"
                : "Layanan inti normal"
            }
            healthy={overview ? overview.status !== "PERLU_PERHATIAN" : true}
          />
        </div>
      </section>

      <section aria-labelledby="recent-heading" className={cn(surfaceClass, "overflow-hidden")}>
        <div className="flex items-center justify-between border-b border-neutral-800 px-5 py-4 sm:px-6">
          <div>
            <h2 id="recent-heading" className="text-base font-medium text-neutral-100">
              Aktivitas Terakhir
            </h2>
            <p className="mt-1 text-sm text-neutral-500">Aktivitas penting, bukan raw audit log.</p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("activity")}
            className="rounded-md px-2 py-1 text-sm text-neutral-400 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
          >
            Lihat semua
          </button>
        </div>
        <div className="divide-y divide-neutral-800">
          {activity.slice(0, 4).map((event) => (
            <ActivitySummary key={event.id} event={event} />
          ))}
          {activity.length === 0 && (
            <p className="px-5 py-6 text-sm text-neutral-500 sm:px-6">Belum ada aktivitas tercatat.</p>
          )}
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <OverviewShortcut
          label="Semua tugas"
          detail={`${tasks.length} task terbaru`}
          onClick={() => onNavigate("tasks")}
        />
        <OverviewShortcut
          label="Pegawai"
          detail={`${employeeList.length} employee ditampilkan`}
          onClick={() => onNavigate("employees")}
        />
        <OverviewShortcut
          label="Pusat persetujuan"
          detail={`${approvals.filter((approval) => approval.status === "Pending").length} menunggu`}
          onClick={() => onNavigate("approvals")}
        />
      </div>
    </PageFrame>
  );
}

interface TasksPageProps {
  selectedTask: SupervisorTask | null;
  onSelect: (task: SupervisorTask | null) => void;
}

export function TasksPage({ selectedTask, onSelect }: TasksPageProps) {
  const { tasks } = useSupervisorData();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"All" | TaskStatus>("All");

  const filteredTasks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return tasks.filter((task) => {
      const matchesFilter = filter === "All" || task.status === filter;
      const matchesQuery =
        !normalizedQuery ||
        `${task.user} ${task.title} ${task.device} ${task.id}`
          .toLowerCase()
          .includes(normalizedQuery);
      return matchesFilter && matchesQuery;
    });
  }, [filter, query, tasks]);

  if (selectedTask) {
    return <TaskDetail task={selectedTask} onBack={() => onSelect(null)} />;
  }

  return (
    <PageFrame>
      <PageIntro
        title="Tugas"
        description="Pantau pekerjaan aktif, progress, dan kegagalan yang membutuhkan tindak lanjut."
        aside={<DemoLabel />}
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex max-w-full gap-1 overflow-x-auto pb-1" aria-label="Filter status tugas">
          {(["All", "Running", "Waiting", "Completed", "Failed"] as const).map((status) => (
            <FilterButton
              key={status}
              active={filter === status}
              onClick={() => setFilter(status)}
            >
              {status === "All" ? "Semua" : TASK_STATUS_ID[status]}
            </FilterButton>
          ))}
        </div>
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Cari tugas..."
          label="Cari tugas"
        />
      </div>

      {filteredTasks.length ? (
        <div className={cn(surfaceClass, "overflow-hidden")}>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead>
                <tr className="border-b border-neutral-800 text-xs font-medium text-neutral-500">
                  <th className="px-5 py-3 font-medium">Pengguna</th>
                  <th className="px-5 py-3 font-medium">Tugas</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Progress</th>
                  <th className="px-5 py-3 font-medium">Diperbarui</th>
                  <th className="w-12 px-5 py-3"><span className="sr-only">Detail</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {filteredTasks.map((task) => (
                  <tr key={task.id} className="group transition-colors hover:bg-neutral-900/70">
                    <td className="px-5 py-4 text-sm text-neutral-300">{task.user}</td>
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        onClick={() => onSelect(task)}
                        className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
                      >
                        <span className="block text-sm font-medium text-neutral-100 group-hover:text-white">
                          {task.title}
                        </span>
                        <span className="mt-1 block text-xs text-neutral-600">{task.id}</span>
                      </button>
                    </td>
                    <td className="px-5 py-4"><TaskStatusLabel status={task.status} /></td>
                    <td className="px-5 py-4"><TaskProgress task={task} /></td>
                    <td className="px-5 py-4 text-sm text-neutral-500">{task.updated}</td>
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        aria-label={`Lihat ${task.title}`}
                        onClick={() => onSelect(task)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.97]"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-neutral-800 md:hidden">
            {filteredTasks.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => onSelect(task)}
                className="w-full px-4 py-4 text-left transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 active:bg-neutral-900"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="text-sm font-medium text-neutral-100">{task.title}</span>
                    <span className="mt-1 block text-xs text-neutral-500">{task.user} · {task.device}</span>
                  </div>
                  <TaskStatusLabel status={task.status} />
                </div>
                <div className="mt-4"><TaskProgress task={task} /></div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Tidak ada tugas yang cocok"
          description="Ubah filter atau kata pencarian untuk melihat tugas lain."
          onReset={() => {
            setFilter("All");
            setQuery("");
          }}
        />
      )}
    </PageFrame>
  );
}

function TaskDetail({ task, onBack }: { task: SupervisorTask; onBack: () => void }) {
  return (
    <PageFrame>
      <BackButton onClick={onBack}>Kembali ke Tugas</BackButton>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageIntro
          title={task.title}
          description={`${task.id} · Diperbarui ${task.updated}`}
        />
        <TaskStatusLabel status={task.status} prominent />
      </div>

      {task.error && (
        <div className="flex gap-3 rounded-xl border border-red-400/20 bg-red-400/[0.06] p-4 text-red-100">
          <CircleX className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium">Task tidak dapat diselesaikan</p>
            <p className="mt-1 text-sm leading-6 text-red-200/70">{task.error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(320px,1.1fr)]">
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="task-info-heading">
          <h2 id="task-info-heading" className="text-base font-medium text-neutral-100">Informasi tugas</h2>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Pengguna" value={task.user} />
            <DefinitionRow label="Perangkat" value={task.device} />
            <DefinitionRow label="Dimulai" value={task.started} />
            <DefinitionRow label="Status" value={<TaskStatusLabel status={task.status} />} />
          </dl>
          <div className="mt-6 border-t border-neutral-800 pt-5">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-xs text-neutral-500">Progress</p>
                <p className="mt-2 text-2xl font-medium tracking-tight text-neutral-100">
                  {task.processed} <span className="text-base text-neutral-600">/ {task.total}</span>
                </p>
              </div>
              <span className="text-sm text-neutral-400">{task.progress === null ? "Berhenti" : `${task.progress}%`}</span>
            </div>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-neutral-800">
              <div
                className={cn("h-full rounded-full", task.status === "Failed" ? "bg-red-400" : "bg-violet-400")}
                style={{ width: `${task.progress ?? Math.round((task.processed / task.total) * 100)}%` }}
              />
            </div>
          </div>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="task-activity-heading">
          <h2 id="task-activity-heading" className="text-base font-medium text-neutral-100">Aktivitas</h2>
          <ol className="mt-6 space-y-0">
            {task.activity.map((step, index) => (
              <li key={step.label} className="relative flex gap-4 pb-6 last:pb-0">
                {index < task.activity.length - 1 && (
                  <span className="absolute left-[9px] top-6 h-[calc(100%-18px)] w-px bg-neutral-800" />
                )}
                <TaskStepIcon state={step.state} />
                <div className="min-w-0 pt-0.5">
                  <p className={cn("text-sm", step.state === "pending" ? "text-neutral-600" : "text-neutral-200")}>{step.label}</p>
                  {step.state === "current" && <p className="mt-1 text-xs text-violet-300">Sedang berjalan</p>}
                  {step.state === "failed" && <p className="mt-1 text-xs text-red-300">Perlu ditinjau</p>}
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <details className={cn(surfaceClass, "group overflow-hidden")}>
        <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 text-sm text-neutral-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50">
          Detail teknis          <ChevronRight className="h-4 w-4 text-neutral-600 transition-transform duration-150 group-open:rotate-90" />
        </summary>
        <dl className="grid gap-4 border-t border-neutral-800 px-5 py-5 text-sm sm:grid-cols-3">
          <DefinitionBlock label="ID Tugas" value={task.id} mono />
          <DefinitionBlock label="Perangkat" value={task.device} mono />
          <DefinitionBlock label="Verifikasi" value={task.status === "Completed" ? "Terverifikasi" : "Menunggu"} />
        </dl>
      </details>
    </PageFrame>
  );
}

interface EmployeesPageProps {
  selectedEmployee: Employee | null;
  onSelect: (employee: Employee | null) => void;
  onTaskSelect: (task: SupervisorTask) => void;
}

export function EmployeesPage({ selectedEmployee, onSelect, onTaskSelect }: EmployeesPageProps) {
  const { employees: employeeList } = useSupervisorData();
  const [query, setQuery] = useState("");
  const filteredEmployees = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return employeeList;
    return employeeList.filter((employee) =>
      `${employee.name} ${employee.email} ${employee.device}`
        .toLowerCase()
        .includes(normalizedQuery),
    );
  }, [employeeList, query]);

  if (selectedEmployee) {
    return (
      <EmployeeDetail
        employee={selectedEmployee}
        onBack={() => onSelect(null)}
        onTaskSelect={onTaskSelect}
      />
    );
  }

  return (
    <PageFrame>
      <PageIntro
        title="Pegawai"
        description="Status account, device, dan pekerjaan tanpa membuka file atau percakapan privat."
        aside={<DemoLabel />}
      />
      <div className="flex justify-end">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Cari pegawai..."
          label="Cari pegawai"
        />
      </div>

      {filteredEmployees.length ? (
        <div className={cn(surfaceClass, "overflow-hidden")}>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[680px] border-collapse text-left">
              <thead>
                <tr className="border-b border-neutral-800 text-xs text-neutral-500">
                  <th className="px-5 py-3 font-medium">Pegawai</th>
                  <th className="px-5 py-3 font-medium">Perangkat</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Tugas</th>
                  <th className="px-5 py-3 font-medium">Terakhir terlihat</th>
                  <th className="w-12 px-5 py-3"><span className="sr-only">Detail</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {filteredEmployees.map((employee) => (
                  <tr key={employee.id} className="group transition-colors hover:bg-neutral-900/70">
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        onClick={() => onSelect(employee)}
                        className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
                      >
                        <span className="block text-sm font-medium text-neutral-100">{employee.name}</span>
                        <span className="mt-1 block text-xs text-neutral-600">{employee.email}</span>
                      </button>
                    </td>
                    <td className="px-5 py-4 text-sm text-neutral-400">{employee.device}</td>
                    <td className="px-5 py-4"><EmployeeStatusLabel status={employee.status} /></td>
                    <td className="px-5 py-4 text-sm text-neutral-300">{employee.tasks ?? "—"}</td>
                    <td className="px-5 py-4 text-sm text-neutral-500">{employee.lastSeen}</td>
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        aria-label={`Lihat ${employee.name}`}
                        onClick={() => onSelect(employee)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.97]"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-neutral-800 md:hidden">
            {filteredEmployees.map((employee) => (
              <button
                key={employee.id}
                type="button"
                onClick={() => onSelect(employee)}
                className="w-full px-4 py-4 text-left transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 active:bg-neutral-900"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="text-sm font-medium text-neutral-100">{employee.name}</span>
                    <span className="mt-1 block text-xs text-neutral-500">{employee.device}</span>
                  </div>
                  <EmployeeStatusLabel status={employee.status} />
                </div>
                <p className="mt-4 text-xs text-neutral-600">{employee.tasks ?? "Tidak ada"} tugas aktif · {employee.lastSeen}</p>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Pegawai tidak ditemukan"
          description="Periksa nama, email, atau nama device yang dicari."
          onReset={() => setQuery("")}
        />
      )}
    </PageFrame>
  );
}

function EmployeeDetail({
  employee,
  onBack,
  onTaskSelect,
}: {
  employee: Employee;
  onBack: () => void;
  onTaskSelect: (task: SupervisorTask) => void;
}) {
  const { tasks } = useSupervisorData();
  const activeTask = tasks.find((task) => task.id === employee.activeTaskId);

  return (
    <PageFrame>
      <BackButton onClick={onBack}>Kembali ke Pegawai</BackButton>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageIntro title={employee.name} description={employee.email} />
        <EmployeeStatusLabel status={employee.status} prominent />
      </div>

      {employee.status === "Offline" && (
        <div className="flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-amber-100">
          <WifiOff className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium">Device sedang offline</p>
            <p className="mt-1 text-sm leading-6 text-amber-200/70">Heartbeat terakhir diterima {employee.lastSeen}.</p>
          </div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="employee-account-heading">
          <div className="flex items-center gap-3">
            <UserRound className="h-5 w-5 text-neutral-500" />
            <h2 id="employee-account-heading" className="text-base font-medium text-neutral-100">Akun</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Nama" value={employee.name} />
            <DefinitionRow label="Email" value={employee.email} />
            <DefinitionRow label="ID Akun" value={employee.id} mono />
          </dl>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="employee-device-heading">
          <div className="flex items-center gap-3">
            <Laptop className="h-5 w-5 text-neutral-500" />
            <h2 id="employee-device-heading" className="text-base font-medium text-neutral-100">Perangkat</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Perangkat" value={employee.device} mono />
            <DefinitionRow label="Sistem operasi" value={employee.os} />
            <DefinitionRow label="Versi agent" value={employee.agentVersion} mono />
            <DefinitionRow label="Koneksi" value={<EmployeeStatusLabel status={employee.status} />} />
          </dl>
        </section>
      </div>

      {activeTask && (
        <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="active-task-heading">
          <div className="border-b border-neutral-800 px-5 py-4 sm:px-6">
            <h2 id="active-task-heading" className="text-base font-medium text-neutral-100">Tugas aktif</h2>
          </div>
          <button
            type="button"
            onClick={() => onTaskSelect(activeTask)}
            className="flex w-full items-center justify-between gap-4 px-5 py-5 text-left transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 sm:px-6"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-neutral-100">{activeTask.title}</p>
              <p className="mt-1 text-xs text-neutral-500">{activeTask.id} · {activeTask.device}</p>
            </div>
            <div className="flex flex-shrink-0 items-center gap-3">
              <TaskStatusLabel status={activeTask.status} />
              <ChevronRight className="h-4 w-4 text-neutral-600" />
            </div>
          </button>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="employee-recent-heading">
          <h2 id="employee-recent-heading" className="text-base font-medium text-neutral-100">Aktivitas terakhir</h2>
          <ul className="mt-4 divide-y divide-neutral-800">
            {employee.recentActivity.map((item) => (
              <li key={item} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                <CircleCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-neutral-500" />
                <span className="text-sm leading-6 text-neutral-300">{item}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="employee-error-heading">
          <h2 id="employee-error-heading" className="text-base font-medium text-neutral-100">Error terkait</h2>
          {employee.errors.length ? (
            <ul className="mt-4 space-y-3">
              {employee.errors.map((error) => (
                <li key={error} className="flex gap-3 rounded-lg bg-red-400/[0.06] p-3 text-sm leading-6 text-red-200">
                  <AlertTriangle className="mt-1 h-4 w-4 flex-shrink-0" />
                  {error}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-4 flex items-center gap-3 rounded-lg bg-emerald-400/[0.05] p-3 text-sm text-emerald-200">
              <CheckCircle2 className="h-4 w-4" />
              Tidak ada error relevan.
            </div>
          )}
        </section>
      </div>

      <div className="flex gap-3 rounded-xl border border-neutral-800 bg-neutral-950 p-4 text-sm leading-6 text-neutral-500">
        <ShieldCheck className="mt-0.5 h-5 w-5 flex-shrink-0 text-violet-300" />
        Supervisor hanya melihat status operasional yang diizinkan. Isi file dan percakapan privat employee tidak ditampilkan.
      </div>
    </PageFrame>
  );
}

interface DevicesPageProps {
  selectedDevice: Device | null;
  onSelect: (device: Device | null) => void;
  onTaskSelect: (task: SupervisorTask) => void;
}

export function DevicesPage({ selectedDevice, onSelect, onTaskSelect }: DevicesPageProps) {
  const { devices: deviceList } = useSupervisorData();
  const [query, setQuery] = useState("");
  const filteredDevices = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return deviceList;
    return deviceList.filter((device) =>
      `${device.name} ${device.owner} ${device.ownerEmail} ${device.os}`
        .toLowerCase()
        .includes(normalizedQuery),
    );
  }, [deviceList, query]);

  if (selectedDevice) {
    return (
      <DeviceDetail
        device={selectedDevice}
        onBack={() => onSelect(null)}
        onTaskSelect={onTaskSelect}
      />
    );
  }

  return (
    <PageFrame>
      <PageIntro
        title="Perangkat"
        description="Kesehatan koneksi, versi agent, dan task aktif setiap device tanpa membuka file user."
        aside={<DemoLabel />}
      />
      <div className="flex justify-end">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Cari device..."
          label="Cari device"
        />
      </div>

      {filteredDevices.length ? (
        <div className={cn(surfaceClass, "overflow-hidden")}>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[720px] border-collapse text-left">
              <thead>
                <tr className="border-b border-neutral-800 text-xs text-neutral-500">
                  <th className="px-5 py-3 font-medium">Perangkat</th>
                  <th className="px-5 py-3 font-medium">Pemilik</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Agent</th>
                  <th className="px-5 py-3 font-medium">Heartbeat terakhir</th>
                  <th className="w-12 px-5 py-3"><span className="sr-only">Detail</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {filteredDevices.map((device) => (
                  <tr key={device.id} className="group transition-colors hover:bg-neutral-900/70">
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        onClick={() => onSelect(device)}
                        className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
                      >
                        <span className="block font-mono text-xs text-neutral-100">{device.name}</span>
                        <span className="mt-1 block text-xs text-neutral-600">{device.os}</span>
                      </button>
                    </td>
                    <td className="px-5 py-4 text-sm text-neutral-400">{device.owner}</td>
                    <td className="px-5 py-4"><EmployeeStatusLabel status={device.status} /></td>
                    <td className="px-5 py-4 font-mono text-xs text-neutral-400">{device.agentVersion}</td>
                    <td className="px-5 py-4 text-sm text-neutral-500">{device.lastHeartbeat}</td>
                    <td className="px-5 py-4">
                      <button
                        type="button"
                        aria-label={`Lihat ${device.name}`}
                        onClick={() => onSelect(device)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.97]"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-neutral-800 md:hidden">
            {filteredDevices.map((device) => (
              <button
                key={device.id}
                type="button"
                onClick={() => onSelect(device)}
                className="w-full px-4 py-4 text-left transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 active:bg-neutral-900"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="font-mono text-xs text-neutral-100">{device.name}</span>
                    <span className="mt-1 block text-xs text-neutral-500">{device.owner}</span>
                  </div>
                  <EmployeeStatusLabel status={device.status} />
                </div>
                <p className="mt-4 text-xs text-neutral-600">Heartbeat {device.lastHeartbeat} · Agent {device.agentVersion}</p>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Perangkat tidak ditemukan"
          description="Periksa nama device, pemilik, atau sistem operasi yang dicari."
          onReset={() => setQuery("")}
        />
      )}
    </PageFrame>
  );
}

function DeviceDetail({
  device,
  onBack,
  onTaskSelect,
}: {
  device: Device;
  onBack: () => void;
  onTaskSelect: (task: SupervisorTask) => void;
}) {
  const { tasks } = useSupervisorData();
  const activeTask = device.activeTaskId
    ? tasks.find((task) => task.id === device.activeTaskId)
    : undefined;

  return (
    <PageFrame>
      <BackButton onClick={onBack}>Kembali ke Perangkat</BackButton>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageIntro title={device.name} description={`${device.os} · Agent ${device.agentVersion}`} />
        <EmployeeStatusLabel status={device.status} prominent />
      </div>

      {device.status === "Offline" && (
        <div className="flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-amber-100">
          <WifiOff className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium">Device sedang offline</p>
            <p className="mt-1 text-sm leading-6 text-amber-200/70">Heartbeat terakhir diterima {device.lastHeartbeat}.</p>
          </div>
        </div>
      )}

      {device.status === "Warning" && (
        <div className="flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-amber-100">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium">Device membutuhkan perhatian</p>
            <p className="mt-1 text-sm leading-6 text-amber-200/70">Ada task atau error yang perlu ditinjau pada {device.name}.</p>
          </div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="device-info-heading">
          <div className="flex items-center gap-3">
            <Laptop className="h-5 w-5 text-neutral-500" />
            <h2 id="device-info-heading" className="text-base font-medium text-neutral-100">Perangkat</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Perangkat" value={device.name} mono />
            <DefinitionRow label="ID Perangkat" value={device.id} mono />
            <DefinitionRow label="Sistem operasi" value={device.os} />
            <DefinitionRow label="Versi agent" value={device.agentVersion} mono />
          </dl>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="device-connection-heading">
          <div className="flex items-center gap-3">
            <Wifi className="h-5 w-5 text-neutral-500" />
            <h2 id="device-connection-heading" className="text-base font-medium text-neutral-100">Koneksi</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Status" value={<EmployeeStatusLabel status={device.status} />} />
            <DefinitionRow label="Heartbeat terakhir" value={device.lastHeartbeat} />
            <DefinitionRow label="Pemilik" value={device.owner} />
            <DefinitionRow label="Email pemilik" value={device.ownerEmail} />
          </dl>
        </section>
      </div>

      {activeTask && (
        <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="device-task-heading">
          <div className="border-b border-neutral-800 px-5 py-4 sm:px-6">
            <h2 id="device-task-heading" className="text-base font-medium text-neutral-100">Tugas aktif</h2>
          </div>
          <button
            type="button"
            onClick={() => onTaskSelect(activeTask)}
            className="flex w-full items-center justify-between gap-4 px-5 py-5 text-left transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 sm:px-6"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-neutral-100">{activeTask.title}</p>
              <p className="mt-1 text-xs text-neutral-500">{activeTask.id} · {activeTask.user}</p>
            </div>
            <div className="flex flex-shrink-0 items-center gap-3">
              <TaskStatusLabel status={activeTask.status} />
              <ChevronRight className="h-4 w-4 text-neutral-600" />
            </div>
          </button>
        </section>
      )}

      <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="device-capabilities-heading">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-neutral-500" />
          <h2 id="device-capabilities-heading" className="text-base font-medium text-neutral-100">Kapabilitas</h2>
        </div>
        <ul className="mt-4 divide-y divide-neutral-800">
          {device.capabilities.map((capability) => (
            <li key={capability} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <CircleCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-neutral-500" />
              <span className="text-sm leading-6 text-neutral-300">{capability}</span>
            </li>
          ))}
        </ul>
      </section>
    </PageFrame>
  );
}

interface ApprovalsPageProps {
  approvals: ApprovalRequest[];
  selectedApproval: ApprovalRequest | null;
  onSelect: (approval: ApprovalRequest | null) => void;
  onResolve: (id: string, status: Exclude<ApprovalStatus, "Pending">) => void;
}

export function ApprovalsPage({ approvals, selectedApproval, onSelect, onResolve }: ApprovalsPageProps) {
  const [filter, setFilter] = useState<"Pending" | "Resolved">("Pending");
  const pendingCount = approvals.filter((approval) => approval.status === "Pending").length;
  const visibleApprovals = approvals.filter((approval) =>
    filter === "Pending" ? approval.status === "Pending" : approval.status !== "Pending",
  );

  if (selectedApproval) {
    const currentApproval = approvals.find((approval) => approval.id === selectedApproval.id) ?? selectedApproval;
    return (
      <ApprovalDetail
        approval={currentApproval}
        onBack={() => onSelect(null)}
        onResolve={onResolve}
      />
    );
  }

  return (
    <PageFrame>
      <PageIntro
        title="Persetujuan"
        description={`${pendingCount} request menunggu keputusan supervisor.`}
        aside={<DemoLabel />}
      />

      <div className="flex gap-1" aria-label="Filter persetujuan">
        <FilterButton active={filter === "Pending"} onClick={() => setFilter("Pending")}>Menunggu</FilterButton>
        <FilterButton active={filter === "Resolved"} onClick={() => setFilter("Resolved")}>Selesai</FilterButton>
      </div>

      {visibleApprovals.length ? (
        <div className="space-y-3">
          {visibleApprovals.map((approval) => (
            <article key={approval.id} className={cn(surfaceClass, "p-5 sm:p-6")}>
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <ApprovalStatusLabel status={approval.status} />
                    <span className="text-xs text-neutral-600">{approval.id}</span>
                  </div>
                  <h2 className="mt-4 text-base font-medium text-neutral-100">{approval.action}</h2>
                  <p className="mt-2 text-sm text-neutral-400">{approval.user} · {approval.device}</p>
                  <p className="mt-4 max-w-2xl text-sm leading-6 text-neutral-500">{approval.reason}</p>
                </div>
                <div className="flex flex-shrink-0 items-center gap-3 sm:flex-col sm:items-end">
                  <span className="text-xs text-neutral-600">Diminta {approval.requested}</span>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onSelect(approval)}
                    className="border-neutral-700 bg-neutral-950 text-neutral-200 hover:bg-neutral-800 hover:text-white active:scale-[0.98]"
                  >
                    {approval.status === "Pending" ? "Tinjau" : "Lihat keputusan"}
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title={filter === "Pending" ? "Tidak ada persetujuan yang menunggu" : "Belum ada keputusan tersimpan"}
          description={filter === "Pending" ? "Request baru akan muncul di sini." : "Persetujuan yang disetujui atau ditolak akan tersimpan di sini."}
        />
      )}
    </PageFrame>
  );
}

function ApprovalDetail({
  approval,
  onBack,
  onResolve,
}: {
  approval: ApprovalRequest;
  onBack: () => void;
  onResolve: (id: string, status: Exclude<ApprovalStatus, "Pending">) => void;
}) {
  const [confirming, setConfirming] = useState<Exclude<ApprovalStatus, "Pending"> | null>(null);

  return (
    <PageFrame>
      <BackButton onClick={onBack}>Kembali ke Persetujuan</BackButton>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageIntro title="Request Persetujuan" description={`${approval.id} · Diminta ${approval.requested}`} />
        <ApprovalStatusLabel status={approval.status} prominent />
      </div>

      {approval.status !== "Pending" && (
        <div className={cn(
          "flex gap-3 rounded-xl border p-4",
          approval.status === "Approved"
            ? "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100"
            : "border-red-400/20 bg-red-400/[0.06] text-red-100",
        )}>
          {approval.status === "Approved" ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
          <p className="text-sm font-medium">Keputusan tercatat: {APPROVAL_STATUS_ID[approval.status]}</p>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="approval-detail-heading">
          <h2 id="approval-detail-heading" className="text-base font-medium text-neutral-100">Detail request</h2>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Pengguna" value={approval.user} />
            <DefinitionRow label="Perangkat" value={approval.device} mono />
            <DefinitionRow label="Aksi" value={approval.action} />
            <DefinitionRow label="Alasan" value={approval.reason} />
            <DefinitionRow label="Scope" value={<span className="break-all font-mono text-xs">{approval.scope}</span>} />
          </dl>
        </section>

        <aside className={cn(
          "h-fit rounded-xl border p-5 sm:p-6",
          approval.destructive
            ? "border-red-400/25 bg-red-400/[0.05]"
            : "border-amber-400/20 bg-amber-400/[0.04]",
        )}>
          <div className="flex items-center gap-3">
            <AlertTriangle className={cn("h-5 w-5", approval.destructive ? "text-red-300" : "text-amber-300")} />
            <h2 className="text-base font-medium text-neutral-100">Risiko</h2>
          </div>
          <p className="mt-4 text-sm leading-6 text-neutral-300">{approval.risk}</p>
          <p className="mt-3 text-xs leading-5 text-neutral-500">Periksa action dan scope sebelum membuat keputusan.</p>
        </aside>
      </div>

      {approval.status === "Pending" && (
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="approval-decision-heading">
          <h2 id="approval-decision-heading" className="text-base font-medium text-neutral-100">Keputusan supervisor</h2>
          {!confirming ? (
            <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => setConfirming("Rejected")}
                className="border-red-400/30 bg-transparent text-red-200 hover:bg-red-400/10 hover:text-red-100 active:scale-[0.98]"
              >
                Tolak
              </Button>
              <Button
                type="button"
                onClick={() => setConfirming("Approved")}
                className="bg-neutral-100 text-neutral-950 hover:bg-white active:scale-[0.98]"
              >
                Setujui
              </Button>
            </div>
          ) : (
            <div className="mt-5 rounded-lg border border-neutral-800 bg-neutral-950 p-4">
              <p className="text-sm font-medium text-neutral-100">
                {confirming === "Approved" ? "Setujui request ini?" : "Tolak request ini?"}
              </p>
              <p className="mt-2 text-sm leading-6 text-neutral-500">
                Keputusan akan dicatat di log aktivitas dan diteruskan ke task terkait.
              </p>
              <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setConfirming(null)}
                  className="text-neutral-400 hover:bg-neutral-900 hover:text-white"
                >
                  Batal
                </Button>
                <Button
                  type="button"
                  onClick={() => {
                    onResolve(approval.id, confirming);
                    setConfirming(null);
                  }}
                  className={cn(
                    "active:scale-[0.98]",
                    confirming === "Approved"
                      ? "bg-neutral-100 text-neutral-950 hover:bg-white"
                      : "bg-red-500 text-white hover:bg-red-400",
                  )}
                >
                  {confirming === "Approved" ? "Ya, setujui" : "Ya, tolak"}
                </Button>
              </div>
            </div>
          )}
        </section>
      )}
    </PageFrame>
  );
}

const OPS_STATUS_LABEL: Record<OpsIncidentStatus, string> = {
  OPEN: "Terbuka",
  INVESTIGATING: "Diselidiki",
  AWAITING_APPROVAL: "Menunggu persetujuan",
  APPROVED_FOR_FIX: "Disetujui diperbaiki",
  FIXING: "Diperbaiki",
  VERIFYING: "Diverifikasi",
  AWAITING_DEPLOY_APPROVAL: "Menunggu approval deploy",
  DEPLOYING: "Dideploy",
  RESOLVED: "Selesai",
  REJECTED: "Ditolak",
};

const OPS_SEVERITY_ID: Record<OpsSeverity, string> = {
  CRITICAL: "Kritis",
  HIGH: "Tinggi",
  MEDIUM: "Sedang",
  LOW: "Rendah",
};

export function OperationsPage() {
  const { ops, dispatchIncident, setFreeze, respondOpsApproval } = useSupervisorData();
  const [severityFilter, setSeverityFilter] = useState<"All" | OpsSeverity>("All");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmingFreeze, setConfirmingFreeze] = useState(false);

  const incidents = ops.incidents;
  const agents = ops.agents;
  const frozen = ops.overview?.frozen ?? false;

  const filteredIncidents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return incidents.filter((incident) => {
      const matchesSeverity = severityFilter === "All" || incident.severity === severityFilter;
      const matchesQuery =
        !normalizedQuery ||
        `${incident.id} ${incident.title} ${incident.source} ${incident.resource}`
          .toLowerCase()
          .includes(normalizedQuery);
      return matchesSeverity && matchesQuery;
    });
  }, [incidents, query, severityFilter]);

  const selectedIncident = selectedId
    ? incidents.find((incident) => incident.id === selectedId) ?? null
    : null;
  const activeIncidents = ops.overview?.activeIncidents ?? incidents.length;
  const criticalCount =
    ops.overview?.criticalCount ??
    incidents.filter((incident) => incident.severity === "CRITICAL").length;
  const pendingOpsApprovals = ops.approvals.filter(
    (approval) => approval.status === "Pending",
  ).length;

  const dispatchTriage = (incident: OpsIncident) => {
    void dispatchIncident(incident.id).catch(() => undefined);
  };

  const haltAutomation = () => {
    void setFreeze(true, "Jeda darurat dari konsol supervisor").catch(() => undefined);
    setConfirmingFreeze(false);
  };

  const resumeAutomation = () => {
    void setFreeze(false, "").catch(() => undefined);
  };

  if (selectedIncident) {
    return (
      <IncidentDetail
        incident={selectedIncident}
        onBack={() => setSelectedId(null)}
        onDispatch={() => dispatchTriage(selectedIncident)}
      />
    );
  }

  return (
    <PageFrame>
      <PageIntro
        title="Operasi"
        description="Kesehatan layanan RAPIIN: insiden, keputusan, dan batas tindakan AI di satu tempat."
        aside={<DemoLabel />}
      />

      <section aria-labelledby="ops-metrics-heading">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 id="ops-metrics-heading" className="text-base font-medium text-neutral-100">
              Kesehatan layanan
            </h2>
            <p className="mt-1 text-sm text-neutral-500">Kondisi backend dan automation saat ini.</p>
          </div>
          <span className="hidden text-xs text-neutral-600 sm:block">Diperbarui baru saja</span>
        </div>
        <div className={cn(surfaceClass, "grid grid-cols-2 overflow-hidden [&>*:nth-child(n+3)]:border-t lg:grid-cols-4 lg:[&>*:nth-child(n+3)]:border-t-0")}>
          <Metric
            label="Kondisi"
            value={frozen ? "Dijeda" : criticalCount > 0 ? "Kritis" : "Terganggu"}
            detail={frozen ? "Automation dihentikan" : "Ada insiden aktif"}
          />
          <Metric label="Insiden aktif" value={String(activeIncidents)} detail={`${criticalCount} kritis`} />
          <Metric label="Persetujuan menunggu" value={String(pendingOpsApprovals)} detail="Code fix & deploy" />
          <Metric
            label="Automation"
            value={frozen ? "Dijeda" : "Berjalan"}
            detail={frozen ? "Jeda darurat aktif" : "Perbaikan dan deploy"}
            healthy={!frozen}
          />
        </div>
      </section>

      <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="freeze-heading">
        <div className="flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-start gap-3">
            <OctagonPause className={cn("mt-0.5 h-5 w-5 flex-shrink-0", frozen ? "text-red-300" : "text-neutral-500")} />
            <div>
              <h2 id="freeze-heading" className="text-base font-medium text-neutral-100">Jeda darurat</h2>
              <p className="mt-1 text-sm leading-6 text-neutral-500">
                {frozen
                  ? "Seluruh aksi otomatis dihentikan. Lanjutkan manual setelah risiko jelas."
                  : "Hentikan seluruh aksi otomatis bila ada risiko."}
              </p>
            </div>
          </div>
          {!confirmingFreeze ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => (frozen ? resumeAutomation() : setConfirmingFreeze(true))}
              className={cn(
                "flex-shrink-0 active:scale-[0.98]",
                frozen
                  ? "border-emerald-400/30 bg-transparent text-emerald-200 hover:bg-emerald-400/10 hover:text-emerald-100"
                  : "border-red-400/30 bg-transparent text-red-200 hover:bg-red-400/10 hover:text-red-100",
              )}
            >
              {frozen ? (
                <>
                  <Play className="mr-2 h-4 w-4" /> Lanjutkan automation
                </>
              ) : (
                <>
                  <Pause className="mr-2 h-4 w-4" /> Aktifkan jeda
                </>
              )}
            </Button>
          ) : (
            <div className="flex flex-shrink-0 flex-col-reverse gap-3 sm:flex-row">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setConfirmingFreeze(false)}
                className="text-neutral-400 hover:bg-neutral-900 hover:text-white"
              >
                Batal
              </Button>
              <Button
                type="button"
                onClick={haltAutomation}
                className="bg-red-500 text-white hover:bg-red-400 active:scale-[0.98]"
              >
                Ya, hentikan
              </Button>
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="incident-queue-heading">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 id="incident-queue-heading" className="text-base font-medium text-neutral-100">
              Antrean insiden
            </h2>
            <p className="mt-1 text-sm text-neutral-500">Sinyal yang sama digabung otomatis agar tidak membanjiri.</p>
          </div>
        </div>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex max-w-full gap-1 overflow-x-auto pb-1" aria-label="Filter tingkat insiden">
            {(["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((severity) => (
              <FilterButton
                key={severity}
                active={severityFilter === severity}
                onClick={() => setSeverityFilter(severity)}
              >
                {severity === "All" ? "Semua" : OPS_SEVERITY_ID[severity]}
              </FilterButton>
            ))}
          </div>
          <SearchField
            value={query}
            onChange={setQuery}
            placeholder="Cari insiden..."
            label="Cari insiden"
          />
        </div>

        {filteredIncidents.length ? (
          <div className={cn(surfaceClass, "mt-4 overflow-hidden")}>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[720px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-neutral-800 text-xs text-neutral-500">
                    <th className="px-5 py-3 font-medium">Tingkat</th>
                    <th className="px-5 py-3 font-medium">Insiden</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Sumber</th>
                    <th className="px-5 py-3 font-medium">Terakhir</th>
                    <th className="w-12 px-5 py-3"><span className="sr-only">Detail</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {filteredIncidents.map((incident) => (
                    <tr key={incident.id} className="group transition-colors hover:bg-neutral-900/70">
                      <td className="px-5 py-4"><OpsSeverityLabel severity={incident.severity} /></td>
                      <td className="px-5 py-4">
                        <button
                          type="button"
                          onClick={() => setSelectedId(incident.id)}
                          className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
                        >
                          <span className="block text-sm font-medium text-neutral-100 group-hover:text-white">
                            {incident.title}
                          </span>
                          <span className="mt-1 block text-xs text-neutral-600">
                            {incident.id} · {incident.occurrences}x terjadi
                          </span>
                        </button>
                      </td>
                      <td className="px-5 py-4"><OpsStatusLabel status={incident.status} /></td>
                      <td className="px-5 py-4 font-mono text-xs text-neutral-400">{incident.source}</td>
                      <td className="px-5 py-4 text-sm text-neutral-500">{incident.lastSeen}</td>
                      <td className="px-5 py-4">
                        <button
                          type="button"
                          aria-label={`Lihat ${incident.title}`}
                          onClick={() => setSelectedId(incident.id)}
                          className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.97]"
                        >
                          <ChevronRight className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="divide-y divide-neutral-800 md:hidden">
              {filteredIncidents.map((incident) => (
                <button
                  key={incident.id}
                  type="button"
                  onClick={() => setSelectedId(incident.id)}
                  className="w-full px-4 py-4 text-left transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 active:bg-neutral-900"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <span className="block text-sm font-medium text-neutral-100">{incident.title}</span>
                      <span className="mt-1 block text-xs text-neutral-500">{incident.id} · {incident.lastSeen}</span>
                    </div>
                    <OpsSeverityLabel severity={incident.severity} />
                  </div>
                  <div className="mt-4"><OpsStatusLabel status={incident.status} /></div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-4">
            <EmptyState
              title="Tidak ada insiden yang cocok"
              description="Ubah filter severity atau kata pencarian untuk melihat insiden lain."
              onReset={() => {
                setSeverityFilter("All");
                setQuery("");
              }}
            />
          </div>
        )}
      </section>

      <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="ops-approval-heading">
        <div className="flex items-center justify-between border-b border-neutral-800 px-5 py-4 sm:px-6">
          <div>
              <h2 id="ops-approval-heading" className="text-base font-medium text-neutral-100">
              Antrean persetujuan
            </h2>
            <p className="mt-1 text-sm text-neutral-500">Code fix dan deployment selalu diputuskan terpisah.</p>
          </div>
          <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-amber-400/10 px-2 text-xs font-medium text-amber-200">
            {pendingOpsApprovals}
          </span>
        </div>
        <div className="divide-y divide-neutral-800">
          {ops.approvals
            .filter((approval) => approval.status === "Pending")
            .map((approval) => (
              <OpsApprovalRow
                key={approval.id}
                approval={approval}
                onResolve={(id, status, password) =>
                  respondOpsApproval(
                    id,
                    status === "Approved" ? "APPROVED" : "REJECTED",
                    password,
                  )
                }
              />
            ))}
          {pendingOpsApprovals === 0 && (
            <p className="px-5 py-6 text-sm text-neutral-500 sm:px-6">Tidak ada persetujuan yang menunggu.</p>
          )}
        </div>
      </section>

      <section aria-labelledby="ops-agents-heading">
        <div className="mb-3">
          <h2 id="ops-agents-heading" className="text-base font-medium text-neutral-100">
            Batas tindakan AI agent
          </h2>
          <p className="mt-1 text-sm text-neutral-500">Empat agent dengan peran tetap. Policy ini ditegakkan server-side.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {agents.map((agent) => (
            <OpsAgentCard key={agent.role} agent={agent} />
          ))}
        </div>
        <div className="mt-4 flex gap-3 rounded-xl border border-neutral-800 bg-neutral-950 p-4 text-sm leading-6 text-neutral-500">
          <Info className="mt-0.5 h-5 w-5 flex-shrink-0 text-violet-300" />
          CODER hanya bekerja di worktree terisolasi setelah Anda menyetujui code fix. Tidak ada agent yang boleh deploy langsung.
        </div>
      </section>
    </PageFrame>
  );
}

function IncidentDetail({
  incident,
  onBack,
  onDispatch,
}: {
  incident: OpsIncident;
  onBack: () => void;
  onDispatch: () => void;
}) {
  const hasLead = incident.assigned.includes("LEAD");

  return (
    <PageFrame>
      <BackButton onClick={onBack}>Kembali ke Operations</BackButton>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageIntro title={incident.title} description={`${incident.id} · Terakhir ${incident.lastSeen}`} />
        <div className="flex flex-wrap gap-2">
          <OpsSeverityLabel severity={incident.severity} prominent />
          <OpsStatusLabel status={incident.status} prominent />
        </div>
      </div>

      <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="incident-summary-heading">
        <h2 id="incident-summary-heading" className="text-base font-medium text-neutral-100">Ringkasan</h2>
        <p className="mt-3 text-sm leading-6 text-neutral-300">{incident.summary}</p>
        <dl className="mt-5 divide-y divide-neutral-800 border-t border-neutral-800">
          <DefinitionRow label="Source" value={incident.source} mono />
          <DefinitionRow label="Resource" value={incident.resource} mono />
          <DefinitionRow label="Occurrences" value={`${incident.occurrences}x`} />
          <DefinitionRow label="First seen" value={incident.firstSeen} />
          <DefinitionRow label="Last seen" value={incident.lastSeen} />
        </dl>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="incident-agents-heading">
          <div className="flex items-center gap-3">
            <ServerCog className="h-5 w-5 text-neutral-500" />
            <h2 id="incident-agents-heading" className="text-base font-medium text-neutral-100">Assigned agents</h2>
          </div>
          {incident.assigned.length ? (
            <ul className="mt-4 space-y-2">
              {incident.assigned.map((role) => (
                <li key={role} className="flex items-center gap-3 rounded-lg bg-neutral-950/60 px-3 py-2.5">
                  <OpsRoleIcon role={role} />
                  <span className="font-mono text-xs text-neutral-100">{role}</span>
                  <OpsAgentStateLabel active />
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm leading-6 text-neutral-500">Belum ada agent yang ditugaskan.</p>
          )}
          {!hasLead && (
            <Button
              type="button"
              onClick={onDispatch}
              className="mt-4 bg-neutral-100 text-neutral-950 hover:bg-white active:scale-[0.98]"
            >
              <CirclePlay className="mr-2 h-4 w-4" /> Dispatch triase
            </Button>
          )}
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="incident-timeline-heading">
          <div className="flex items-center gap-3">
            <Clock3 className="h-5 w-5 text-neutral-500" />
            <h2 id="incident-timeline-heading" className="text-base font-medium text-neutral-100">Timeline</h2>
          </div>
          <ol className="mt-6 space-y-0">
            {incident.timeline.map((event, index) => (
              <li key={`${event.time}-${index}`} className="relative flex gap-4 pb-6 last:pb-0">
                {index < incident.timeline.length - 1 && (
                  <span className="absolute left-[9px] top-6 h-[calc(100%-18px)] w-px bg-neutral-800" />
                )}
                <Circle className="relative z-10 h-5 w-5 flex-shrink-0 bg-neutral-900 p-1 text-neutral-500" />
                <div className="min-w-0 pt-0.5">
                  <p className="text-sm text-neutral-200">{event.label}</p>
                  <p className="mt-1 text-xs text-neutral-600">{event.time} · {event.actor}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </PageFrame>
  );
}

function OpsApprovalRow({
  approval,
  onResolve,
}: {
  approval: OpsApproval;
  onResolve: (
    id: string,
    status: Exclude<ApprovalStatus, "Pending">,
    password: string,
  ) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState<Exclude<ApprovalStatus, "Pending"> | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setConfirming(null);
    setPassword("");
    setError("");
  };

  const submit = async () => {
    if (!confirming) return;
    setSubmitting(true);
    setError("");
    try {
      await onResolve(approval.id, confirming, password);
      reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Keputusan tidak dapat dikirim.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="px-5 py-5 sm:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-400/10 px-2.5 py-1 text-xs font-medium text-violet-200">
          <SquareTerminal className="h-3.5 w-3.5" />
          {approval.kind === "CODE_FIX" ? "Code fix" : "Deployment"}
        </span>
        <span className="text-xs text-neutral-600">{approval.id} · {approval.incidentId}</span>
        <span className="ml-auto text-xs text-neutral-600">Diminta {approval.requested}</span>
      </div>
      <h3 className="mt-3 text-base font-medium text-neutral-100">{approval.title}</h3>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-500">{approval.description}</p>
      <p className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-neutral-500">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-300" />
        {approval.risk}
      </p>

      {!confirming ? (
        <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={() => setConfirming("Rejected")}
            className="border-red-400/30 bg-transparent text-red-200 hover:bg-red-400/10 hover:text-red-100 active:scale-[0.98]"
          >
            Tolak
          </Button>
          <Button
            type="button"
            onClick={() => setConfirming("Approved")}
            className="bg-neutral-100 text-neutral-950 hover:bg-white active:scale-[0.98]"
          >
            Setujui
          </Button>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-neutral-800 bg-neutral-950 p-4">
          <p className="text-sm font-medium text-neutral-100">
            {confirming === "Approved" ? "Setujui request ini?" : "Tolak request ini?"}
          </p>
          <p className="mt-2 text-sm leading-6 text-neutral-500">
            {approval.kind === "CODE_FIX"
              ? "CODER hanya bekerja di worktree terisolasi setelah persetujuan ini."
              : "Deployment ke production dicatat dan dapat di-rollback."}
          </p>
          {confirming === "Approved" && (
            <div className="mt-4 space-y-2">
              <label
                htmlFor={`ops-approval-password-${approval.id}`}
                className="block text-sm font-medium text-neutral-300"
              >
                Konfirmasi kata sandi supervisor
              </label>
              <input
                id={`ops-approval-password-${approval.id}`}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setError("");
                }}
                placeholder="Masukkan kata sandi Anda"
                className={inputClass}
              />
              {error && (
                <p role="alert" className="text-sm leading-5 text-red-300">
                  {error}
                </p>
              )}
            </div>
          )}
          {confirming === "Rejected" && error && (
            <p role="alert" className="mt-3 text-sm leading-5 text-red-300">
              {error}
            </p>
          )}
          <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={reset}
              className="text-neutral-400 hover:bg-neutral-900 hover:text-white"
            >
              Batal
            </Button>
            <Button
              type="button"
              disabled={submitting || (confirming === "Approved" && !password)}
              onClick={submit}
              className={cn(
                "active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60",
                confirming === "Approved"
                  ? "bg-neutral-100 text-neutral-950 hover:bg-white"
                  : "bg-red-500 text-white hover:bg-red-400",
              )}
            >
              {confirming === "Approved" ? "Ya, setujui" : "Ya, tolak"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function OpsAgentCard({ agent }: { agent: OpsAgent }) {
  return (
    <article className={cn(surfaceClass, "p-5 sm:p-6")}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-400/10 text-violet-200">
            <OpsRoleIcon role={agent.role} large />
          </span>
          <div>
            <h3 className="font-mono text-sm font-medium text-neutral-100">{agent.role}</h3>
            <p className="mt-0.5 text-xs text-neutral-500">{agent.purpose}</p>
          </div>
        </div>
        <OpsAgentStateLabel active={agent.state === "ACTIVE"} />
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5" aria-label={`Tools ${agent.role}`}>
        {agent.tools.map((tool) => (
          <code key={tool} className="rounded-md border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-[11px] text-neutral-400">
            {tool}
          </code>
        ))}
      </div>
      <p className="mt-4 border-t border-neutral-800 pt-3 text-xs leading-5 text-neutral-500">{agent.boundary}</p>
    </article>
  );
}

function OpsRoleIcon({ role, large = false }: { role: OpsAgentRole; large?: boolean }) {
  const className = large ? "h-5 w-5" : "h-4 w-4";
  if (role === "LEAD") return <Radar className={className} aria-hidden="true" />;
  if (role === "SECURITY") return <ShieldHalf className={className} aria-hidden="true" />;
  if (role === "DIAGNOSTIC") return <Stethoscope className={className} aria-hidden="true" />;
  return <SquareTerminal className={className} aria-hidden="true" />;
}

function OpsSeverityLabel({ severity, prominent = false }: { severity: OpsSeverity; prominent?: boolean }) {
  const config: Record<OpsSeverity, { icon: ReactNode; className: string }> = {
    CRITICAL: { icon: <Siren className="h-3.5 w-3.5" />, className: "text-red-200 bg-red-400/10" },
    HIGH: { icon: <CircleAlert className="h-3.5 w-3.5" />, className: "text-amber-200 bg-amber-400/10" },
    MEDIUM: { icon: <Info className="h-3.5 w-3.5" />, className: "text-violet-200 bg-violet-400/10" },
    LOW: { icon: <Circle className="h-3.5 w-3.5" />, className: "text-neutral-300 bg-neutral-700/50" },
  };
  return (
    <span className={cn("inline-flex w-fit flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", prominent && "px-3 py-1.5 text-sm", config[severity].className)}>
      {config[severity].icon}{OPS_SEVERITY_ID[severity]}
    </span>
  );
}

function OpsStatusLabel({ status, prominent = false }: { status: OpsIncidentStatus; prominent?: boolean }) {
  const running: OpsIncidentStatus[] = ["INVESTIGATING", "FIXING", "VERIFYING", "DEPLOYING"];
  const waiting: OpsIncidentStatus[] = ["AWAITING_APPROVAL", "APPROVED_FOR_FIX"];
  const className = running.includes(status)
    ? "text-violet-200 bg-violet-400/10"
    : waiting.includes(status)
      ? "text-amber-200 bg-amber-400/10"
      : "text-neutral-300 bg-neutral-700/50";
  return (
    <span className={cn("inline-flex w-fit flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", prominent && "px-3 py-1.5 text-sm", className)}>
      {running.includes(status)
        ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
        : waiting.includes(status)
          ? <Clock3 className="h-3.5 w-3.5" />
          : <Circle className="h-3.5 w-3.5" />}
      {OPS_STATUS_LABEL[status]}
    </span>
  );
}

function OpsAgentStateLabel({ active }: { active: boolean }) {
  return (
    <span className={cn(
      "inline-flex w-fit flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
      active ? "text-emerald-200 bg-emerald-400/10" : "text-neutral-400 bg-neutral-800/60",
    )}>
      <span className={cn("h-1.5 w-1.5 rounded-full", active ? "animate-pulse bg-emerald-300" : "bg-neutral-600")} aria-hidden="true" />
      {active ? "Aktif" : "Siaga"}
    </span>
  );
}

export function ActivityPage() {
  const { activity } = useSupervisorData();
  const [filter, setFilter] = useState<"All" | ActivityEvent["category"]>("All");
  const visibleEvents = activity.filter((event) => filter === "All" || event.category === filter);

  return (
    <PageFrame>
      <PageIntro
        title="Aktivitas"
        description="Timeline aktivitas penting yang dapat dipahami tanpa membaca raw audit table."
        aside={<DemoLabel />}
      />
      <div className="flex max-w-full gap-1 overflow-x-auto pb-1" aria-label="Filter aktivitas">
        {(["All", "Task", "Approval", "Device", "Account"] as const).map((category) => (
          <FilterButton key={category} active={filter === category} onClick={() => setFilter(category)}>
            {category === "All" ? "Semua" : category === "Task" ? "Tugas" : category === "Approval" ? "Persetujuan" : category === "Device" ? "Perangkat" : "Akun"}
          </FilterButton>
        ))}
      </div>

      <section className={cn(surfaceClass, "overflow-hidden")} aria-label="Timeline aktivitas">
        <div className="divide-y divide-neutral-800">
          {visibleEvents.map((event) => (
            <details key={event.id} className="group">
              <summary className="grid cursor-pointer list-none grid-cols-[48px_24px_minmax(0,1fr)_20px] gap-3 px-4 py-5 transition-colors hover:bg-neutral-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 sm:grid-cols-[64px_24px_minmax(0,1fr)_80px_20px] sm:px-6">
                <time className="pt-0.5 text-xs text-neutral-600">{event.time}</time>
                <ActivityToneIcon tone={event.tone} />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-neutral-200">{event.title}</span>
                  {event.detail && <span className="mt-1 block text-sm leading-6 text-neutral-500">{event.detail}</span>}
                </span>
                <span className="hidden pt-0.5 text-right text-xs text-neutral-600 sm:block">{event.category}</span>
                <ChevronRight className="mt-0.5 h-4 w-4 text-neutral-600 transition-transform duration-150 group-open:rotate-90" />
              </summary>
              <dl className="grid gap-4 border-t border-neutral-800 bg-neutral-950/60 px-4 py-5 text-sm sm:grid-cols-3 sm:px-[124px]">
                <DefinitionBlock label="Aktor" value={event.actor} />
                <DefinitionBlock label="Perangkat" value={event.device ?? "Tidak ada"} mono={Boolean(event.device)} />
                <DefinitionBlock label="Tugas" value={event.taskId ?? "Tidak ada"} mono={Boolean(event.taskId)} />
              </dl>
            </details>
          ))}
        </div>
      </section>
    </PageFrame>
  );
}

export function SettingsPage() {
  const [preferences, setPreferences] = useState({
    approvals: true,
    failures: true,
    offline: true,
  });
  const [saved, setSaved] = useState(false);

  const updatePreference = (key: keyof typeof preferences) => {
    setPreferences((current) => ({ ...current, [key]: !current[key] }));
    setSaved(false);
  };

  return (
    <PageFrame narrow>
      <PageIntro title="Pengaturan" description="Pengaturan supervisor yang penting untuk V1." />

      <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="notification-heading">
        <div className="border-b border-neutral-800 px-5 py-4 sm:px-6">
          <h2 id="notification-heading" className="text-base font-medium text-neutral-100">Notifikasi</h2>
          <p className="mt-1 text-sm text-neutral-500">Pilih perubahan yang perlu segera Anda ketahui.</p>
        </div>
        <div className="divide-y divide-neutral-800">
          <NotificationRow
            label="Request persetujuan"
            description="Saat request baru membutuhkan keputusan supervisor."
            checked={preferences.approvals}
            onChange={() => updatePreference("approvals")}
          />
          <NotificationRow
            label="Kegagalan tugas"
            description="Saat task berhenti dan membutuhkan tindak lanjut."
            checked={preferences.failures}
            onChange={() => updatePreference("failures")}
          />
          <NotificationRow
            label="Device offline"
            description="Saat device berhenti mengirim heartbeat."
            checked={preferences.offline}
            onChange={() => updatePreference("offline")}
          />
        </div>
      </section>

      <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="about-heading">
        <h2 id="about-heading" className="text-base font-medium text-neutral-100">Tentang</h2>
        <dl className="mt-5 divide-y divide-neutral-800">
          <DefinitionRow label="Versi RAPIIN" value="1.0.0" mono />
          <DefinitionRow label="Antarmuka" value="Konsol Supervisor" />
          <DefinitionRow label="Lingkungan" value="Server RAPIIN" />
        </dl>
      </section>

      <div className="flex items-center justify-end gap-4">
        {saved && (
          <span role="status" className="inline-flex items-center gap-2 text-sm text-emerald-300">
            <Check className="h-4 w-4" /> Tersimpan
          </span>
        )}
        <Button
          type="button"
          onClick={() => setSaved(true)}
          className="bg-neutral-100 text-neutral-950 hover:bg-white active:scale-[0.98]"
        >
          Simpan perubahan
        </Button>
      </div>
    </PageFrame>
  );
}

export function AccountPage() {
  const { profile, accounts, logout } = useSupervisorData();
  const name = profile?.name ?? "Supervisor";
  const email = profile?.email ?? "—";
  const seat = accounts ? `${accounts.count} dari ${accounts.max}` : "—";
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <PageFrame narrow>
      <PageIntro title="Akun Supervisor" description="Identitas dan scope akses supervisor saat ini." />

      <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="profile-heading">
        <div className="flex items-center gap-4 border-b border-neutral-800 pb-5">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-violet-400/10 text-sm font-semibold text-violet-200">{initials || "—"}</div>
          <div>
            <h2 id="profile-heading" className="text-base font-medium text-neutral-100">{name}</h2>
            <p className="mt-1 text-sm text-neutral-500">Supervisor</p>
          </div>
        </div>
        <dl className="mt-2 divide-y divide-neutral-800">
          <DefinitionRow label="Nama" value={name} />
          <DefinitionRow label="Email" value={email} />
          <DefinitionRow label="Role" value={profile?.role ?? "SUPERVISOR"} mono />
          <DefinitionRow label="Kursi supervisor" value={seat} />
        </dl>
      </section>

      <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="security-heading">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-violet-300" />
          <h2 id="security-heading" className="text-base font-medium text-neutral-100">Akses & keamanan</h2>
        </div>
        <dl className="mt-5 divide-y divide-neutral-800">
          <DefinitionRow label="Sesi saat ini" value="Browser ini" />
          <DefinitionRow label="Status sesi" value={<span className="inline-flex items-center gap-2 text-emerald-300"><CircleCheck className="h-4 w-4" /> Aman</span>} />
          <DefinitionRow label="Kursi terpakai" value={seat} />
        </dl>
      </section>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm leading-6 text-neutral-500">Keluar akan mengakhiri sesi supervisor di browser ini.</p>
        <Button
          type="button"
          variant="outline"
          onClick={logout}
          className="border-neutral-700 bg-transparent text-neutral-200 hover:bg-neutral-800 hover:text-white active:scale-[0.98]"
        >
          <LogOut className="mr-2 h-4 w-4" /> Keluar
        </Button>
      </div>

      <div className="flex gap-3 rounded-xl border border-neutral-800 bg-neutral-950 p-4 text-sm leading-6 text-neutral-500">
        <ShieldCheck className="mt-0.5 h-5 w-5 flex-shrink-0 text-violet-300" />
        Role supervisor memberi akses ke monitoring yang diizinkan, bukan isi file atau percakapan privat employee.
      </div>
    </PageFrame>
  );
}

function PageFrame({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  return (
    <div className={cn("mx-auto flex w-full flex-col gap-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10", narrow ? "max-w-4xl" : "max-w-7xl")}>
      {children}
    </div>
  );
}

function PageIntro({ title, description, aside }: { title: string; description: string; aside?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 sm:text-3xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-500 sm:text-base">{description}</p>
      </div>
      {aside}
    </div>
  );
}

function DemoLabel() {
  return (
    <span className="inline-flex w-fit items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/60 px-3 py-1.5 text-xs text-neutral-500">
      <Circle className="h-2 w-2 fill-violet-300 text-violet-300" /> Data langsung
    </span>
  );
}

function AttentionRow({
  icon,
  tone,
  title,
  detail,
  action,
  onClick,
}: {
  icon: ReactNode;
  tone: "warning" | "danger";
  title: string;
  detail: string;
  action: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-start gap-4 px-5 py-4 text-left transition-colors hover:bg-neutral-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50 active:bg-neutral-900 sm:items-center sm:px-6"
    >
      <span className={cn("mt-0.5 flex-shrink-0 sm:mt-0", tone === "danger" ? "text-red-300" : "text-amber-300")}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-neutral-100">{title}</span>
        <span className="mt-1 block text-sm leading-6 text-neutral-500">{detail}</span>
      </span>
      <span className="hidden flex-shrink-0 items-center gap-1 text-sm text-neutral-500 group-hover:text-neutral-200 sm:flex">
        {action}<ChevronRight className="h-4 w-4" />
      </span>
    </button>
  );
}

function Metric({ label, value, detail, healthy = false }: { label: string; value: string; detail: string; healthy?: boolean }) {
  return (
    <div className="border-neutral-800 p-5 even:border-l lg:border-l lg:first:border-l-0 sm:p-6">
      <p className="text-xs font-medium text-neutral-500">{label}</p>
      <div className="mt-4 flex items-center gap-2">
        {healthy && <CircleCheck className="h-5 w-5 text-emerald-300" />}
        <p className={cn("font-medium tracking-[-0.025em] text-neutral-100", healthy ? "text-xl" : "text-2xl")}>{value}</p>
      </div>
      <p className="mt-2 text-xs text-neutral-600">{detail}</p>
    </div>
  );
}

function ActivitySummary({ event }: { event: ActivityEvent }) {
  return (
    <div className="grid grid-cols-[48px_20px_minmax(0,1fr)] gap-3 px-5 py-4 sm:grid-cols-[64px_20px_minmax(0,1fr)] sm:px-6">
      <time className="pt-0.5 text-xs text-neutral-600">{event.time}</time>
      <ActivityToneIcon tone={event.tone} />
      <div>
        <p className="text-sm text-neutral-200">{event.title}</p>
        {event.detail && <p className="mt-1 text-sm leading-6 text-neutral-500">{event.detail}</p>}
      </div>
    </div>
  );
}

function OverviewShortcut({ label, detail, onClick }: { label: string; detail: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center justify-between gap-3 rounded-xl border border-neutral-800 bg-neutral-900/25 p-4 text-left transition-[border-color,background-color,transform] duration-150 hover:border-neutral-700 hover:bg-neutral-900/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.985]"
    >
      <span>
        <span className="block text-sm font-medium text-neutral-200">{label}</span>
        <span className="mt-1 block text-xs text-neutral-600">{detail}</span>
      </span>
      <ChevronRight className="h-4 w-4 flex-shrink-0 text-neutral-600" />
    </button>
  );
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "h-9 flex-shrink-0 rounded-lg px-3 text-sm transition-[background-color,color,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.97]",
        active ? "bg-neutral-100 text-neutral-950" : "text-neutral-500 hover:bg-neutral-900 hover:text-neutral-200",
      )}
    >
      {children}
    </button>
  );
}

function SearchField({ value, onChange, placeholder, label }: { value: string; onChange: (value: string) => void; placeholder: string; label: string }) {
  return (
    <label className="relative block w-full lg:w-72">
      <span className="sr-only">{label}</span>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-600" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={cn(inputClass, "pl-9")}
      />
    </label>
  );
}

function EmptyState({ title, description, onReset }: { title: string; description: string; onReset?: () => void }) {
  return (
    <div className={cn(surfaceClass, "flex min-h-64 flex-col items-center justify-center px-6 py-12 text-center")}>
      <CircleDashed className="h-7 w-7 text-neutral-600" />
      <h2 className="mt-4 text-base font-medium text-neutral-200">{title}</h2>
      <p className="mt-2 max-w-sm text-sm leading-6 text-neutral-500">{description}</p>
      {onReset && (
          <Button type="button" variant="outline" onClick={onReset} className="mt-5 border-neutral-700 bg-neutral-950 text-neutral-300 hover:bg-neutral-800 hover:text-white">
          Atur ulang filter
        </Button>
      )}
    </div>
  );
}

function BackButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex w-fit items-center gap-2 rounded-md py-1 pr-2 text-sm text-neutral-500 transition-colors hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
    >
      <ArrowLeft className="h-4 w-4" /> {children}
    </button>
  );
}

function DefinitionRow({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-sm text-neutral-600">{label}</dt>
      <dd className={cn("text-sm text-neutral-300 sm:text-right", mono && "font-mono text-xs")}>{value}</dd>
    </div>
  );
}

function DefinitionBlock({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-neutral-600">{label}</dt>
      <dd className={cn("mt-1 text-sm text-neutral-300", mono && "font-mono text-xs")}>{value}</dd>
    </div>
  );
}

function TaskProgress({ task }: { task: SupervisorTask }) {
  const progress = task.progress ?? Math.round((task.processed / task.total) * 100);
  return (
    <div className="w-full min-w-28 max-w-40">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="text-neutral-500">{task.progress === null ? `${task.processed}/${task.total}` : `${task.progress}%`}</span>
        {task.status === "Running" && <span className="text-neutral-600">{task.processed}/{task.total}</span>}
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-neutral-800">
        <div className={cn("h-full rounded-full", task.status === "Failed" ? "bg-red-400" : task.status === "Completed" ? "bg-emerald-400" : "bg-violet-400")} style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

function TaskStatusLabel({ status, prominent = false }: { status: TaskStatus; prominent?: boolean }) {
  const config: Record<TaskStatus, { icon: ReactNode; className: string }> = {
    Running: { icon: <LoaderCircle className="h-3.5 w-3.5 animate-spin" />, className: "text-violet-200 bg-violet-400/10" },
    Waiting: { icon: <Clock3 className="h-3.5 w-3.5" />, className: "text-amber-200 bg-amber-400/10" },
    Completed: { icon: <CheckCircle2 className="h-3.5 w-3.5" />, className: "text-emerald-200 bg-emerald-400/10" },
    Failed: { icon: <CircleX className="h-3.5 w-3.5" />, className: "text-red-200 bg-red-400/10" },
  };
  return (
    <span className={cn("inline-flex w-fit flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", prominent && "px-3 py-1.5 text-sm", config[status].className)}>
      {config[status].icon}{TASK_STATUS_ID[status]}
    </span>
  );
}

function EmployeeStatusLabel({ status, prominent = false }: { status: EmployeeStatus; prominent?: boolean }) {
  const config: Record<EmployeeStatus, { icon: ReactNode; className: string }> = {
    Online: { icon: <Wifi className="h-3.5 w-3.5" />, className: "text-emerald-200 bg-emerald-400/10" },
    Offline: { icon: <WifiOff className="h-3.5 w-3.5" />, className: "text-neutral-300 bg-neutral-700/50" },
    Warning: { icon: <AlertTriangle className="h-3.5 w-3.5" />, className: "text-amber-200 bg-amber-400/10" },
  };
  return (
    <span className={cn("inline-flex w-fit flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", prominent && "px-3 py-1.5 text-sm", config[status].className)}>
      {config[status].icon}{EMPLOYEE_STATUS_ID[status]}
    </span>
  );
}

function ApprovalStatusLabel({ status, prominent = false }: { status: ApprovalStatus; prominent?: boolean }) {
  const config: Record<ApprovalStatus, { icon: ReactNode; className: string }> = {
    Pending: { icon: <Clock3 className="h-3.5 w-3.5" />, className: "text-amber-200 bg-amber-400/10" },
    Approved: { icon: <CheckCircle2 className="h-3.5 w-3.5" />, className: "text-emerald-200 bg-emerald-400/10" },
    Rejected: { icon: <CircleX className="h-3.5 w-3.5" />, className: "text-red-200 bg-red-400/10" },
  };
  return (
    <span className={cn("inline-flex w-fit flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", prominent && "px-3 py-1.5 text-sm", config[status].className)}>
      {config[status].icon}{APPROVAL_STATUS_ID[status]}
    </span>
  );
}

function TaskStepIcon({ state }: { state: SupervisorTask["activity"][number]["state"] }) {
  if (state === "complete") return <CheckCircle2 className="relative z-10 h-5 w-5 flex-shrink-0 bg-neutral-900 text-emerald-300" />;
  if (state === "current") return <LoaderCircle className="relative z-10 h-5 w-5 flex-shrink-0 animate-spin bg-neutral-900 text-violet-300" />;
  if (state === "failed") return <CircleX className="relative z-10 h-5 w-5 flex-shrink-0 bg-neutral-900 text-red-300" />;
  return <Circle className="relative z-10 h-5 w-5 flex-shrink-0 bg-neutral-900 text-neutral-700" />;
}

function ActivityToneIcon({ tone }: { tone: ActivityEvent["tone"] }) {
  if (tone === "success") return <CheckCircle2 className="h-4 w-4 text-emerald-300" />;
  if (tone === "danger") return <CircleX className="h-4 w-4 text-red-300" />;
  if (tone === "warning") return <AlertTriangle className="h-4 w-4 text-amber-300" />;
  return <FileCheck2 className="h-4 w-4 text-violet-300" />;
}

function NotificationRow({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-5 px-5 py-4 sm:px-6">
      <span>
        <span className="block text-sm font-medium text-neutral-200">{label}</span>
        <span className="mt-1 block text-sm leading-6 text-neutral-500">{description}</span>
      </span>
      <span className="relative inline-flex h-6 w-11 flex-shrink-0">
        <input type="checkbox" checked={checked} onChange={onChange} className="peer sr-only" />
        <span className="absolute inset-0 rounded-full bg-neutral-700 transition-colors duration-150 peer-checked:bg-violet-500 peer-focus-visible:ring-2 peer-focus-visible:ring-violet-300 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-neutral-950" />
        <span className="absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform duration-150 peer-checked:translate-x-5" />
      </span>
    </label>
  );
}

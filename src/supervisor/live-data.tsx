"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";
import { clearSession } from "@/lib/session";
import type {
  ActionPolicy,
  Approval,
  AuditEvent,
  Device as ApiDevice,
  Employee as ApiEmployee,
  EmployeeDetail as ApiEmployeeDetail,
  Profile,
  SupervisorAccounts,
  SupervisorOverview,
  Task as ApiTask,
  TaskActivity,
} from "@/lib/types";
import type {
  ActivityEvent,
  ActivityTone,
  ApprovalRequest,
  ApprovalStatus,
  Device,
  Employee,
  EmployeeStatus,
  OpsAgent,
  OpsAgentRole,
  OpsAgentState,
  OpsApproval,
  OpsIncident,
  OpsIncidentStatus,
  OpsSeverity,
  SupervisorTask,
  TaskStatus,
} from "@/src/supervisor/data";

const DESTRUCTIVE_TOOLS = new Set(["file_delete", "bulk_delete", "batch_delete"]);

/** Accounts created by a supervisor start without a paired device. */
export const NO_DEVICE_LABEL = "Belum ada device";

const TASK_STATUS_BY_API: Record<string, TaskStatus> = {
  PENDING: "Waiting",
  PLANNING: "Waiting",
  WAITING_APPROVAL: "Waiting",
  RUNNING: "Running",
  VERIFYING: "Running",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CANCELLED: "Failed",
};

const TASK_TYPE_LABEL: Record<string, string> = {
  conversation: "Percakapan",
  chat: "Percakapan",
  organize: "Merapikan file",
};

const ACTION_LABEL: Record<string, string> = {
  user_message: "mengirim permintaan",
  conversation_created: "membuka percakapan",
  approval_requested: "membutuhkan persetujuan",
  approval_approved: "disetujui",
  approval_rejected: "ditolak",
  approval_executing: "menjalankan tindakan yang disetujui",
  approval_execution_failed: "gagal menjalankan tindakan",
  recommendation_apply_requested: "menerapkan rekomendasi",
  task_cancel_requested: "membatalkan tugas",
  user_registered: "mendaftar",
  login: "masuk",
  login_failed: "gagal masuk",
  logout: "keluar",
  device_rekeyed: "memasangkan ulang device",
  device_revoked: "mencabut device",
  profile_updated: "memperbarui profil",
  policy_updated: "memperbarui policy",
  employee_created: "membuat pegawai",
  employee_state_changed: "mengubah status pegawai",
  supervisor_created: "membuat akun supervisor",
  supervisor_chat: "bertanya ke RAPIIN",
  assistant_reply: "mengirim jawaban",
  agent_error: "mengalami error agent",
  device_registered: "mendaftarkan device",
  task_cancelled: "membatalkan tugas",
  ops_signal_ingested: "menerima sinyal operasi",
  ops_incident_status_changed: "mengubah status insiden",
  ops_incident_auto_resolved: "menutup insiden secara otomatis",
  ops_proposal_created: "membuat proposal operasi",
  ops_approval_decided: "memutuskan approval operasi",
  ops_approval_expired: "membiarkan approval operasi kedaluwarsa",
  ops_emergency_pause_enabled: "mengaktifkan jeda darurat",
  ops_retention_applied: "menerapkan retensi operasi",
};

const OPS_AGENT_PURPOSE: Record<OpsAgentRole, string> = {
  LEAD: "Triase & koordinasi",
  SECURITY: "Review keamanan",
  DIAGNOSTIC: "Kumpulkan bukti",
  CODER: "Perbaiki code yang disetujui",
};

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "Belum pernah";
  const elapsed = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(elapsed)) return "—";
  const seconds = Math.max(0, Math.round(elapsed / 1000));
  if (seconds < 60) return "Baru saja";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  return `${Math.round(hours / 24)} hari lalu`;
}

function clockTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}

function connectionStatus(device: ApiDevice): EmployeeStatus {
  if (device.status !== "ONLINE") return "Offline";
  return device.connection_health === "DEGRADED" ? "Warning" : "Online";
}

function activityTone(result: string | null): ActivityTone {
  if (!result) return "info";
  if (result === "FAILED") return "danger";
  if (result === "PENDING" || result === "DISABLED") return "warning";
  return "success";
}

function activityCategory(action: string): ActivityEvent["category"] {
  if (action.startsWith("approval")) return "Approval";
  if (action.startsWith("device")) return "Device";
  if (action.startsWith("login") || action.startsWith("logout") || action.startsWith("profile") || action.startsWith("employee") || action.startsWith("supervisor") || action.startsWith("user_")) {
    return "Account";
  }
  return "Task";
}

function activityTitle(event: AuditEvent): string {
  const label = ACTION_LABEL[event.action] ?? event.action.replace(/_/g, " ");
  const actor = !event.actor || event.actor === "system" ? "Sistem" : event.actor;
  return `${actor} ${label}`;
}

function mapActivity(events: AuditEvent[]): ActivityEvent[] {
  return events.map((event) => ({
    id: `EVT-${event.id}`,
    time: clockTime(event.timestamp),
    title: activityTitle(event),
    detail: [event.resource, event.error].filter(Boolean).join(" · ") || undefined,
    tone: activityTone(event.result),
    category: activityCategory(event.action),
    actor: event.actor ?? "Sistem",
    device: undefined,
    taskId: event.task_id ? `TASK-${event.task_id}` : undefined,
  }));
}

function toTaskActivity(rows: TaskActivity[]): SupervisorTask["activity"] {
  return rows.map((row) => ({
    label: ACTION_LABEL[row.action] ?? row.action.replace(/_/g, " "),
    state: row.result === "FAILED" ? "failed" : "complete",
  }));
}

function toActivitySteps(rows: TaskActivity[]): SupervisorTask["activity"] {
  const steps = toTaskActivity(rows);
  return steps.reverse();
}

function mapTask(
  task: ApiTask,
  users: Map<number, string>,
  devices: Map<number, string>,
): SupervisorTask {
  return {
    id: `TASK-${task.id}`,
    user: users.get(task.user_id) ?? `User #${task.user_id}`,
    title: TASK_TYPE_LABEL[task.type] ?? task.type,
    status: TASK_STATUS_BY_API[task.status] ?? "Waiting",
    progress: task.progress === null ? null : Math.round(task.progress),
    processed: task.processed_count,
    total: task.total_count,
    device: task.device_id === null ? "—" : devices.get(task.device_id) ?? `Device #${task.device_id}`,
    started: clockTime(task.started_at ?? task.created_at),
    updated: relativeTime(task.completed_at ?? task.started_at ?? task.created_at),
    error: task.error ?? undefined,
    activity: task.activity ? toActivitySteps(task.activity) : [],
  };
}

function mapEmployee(
  employee: ApiEmployee,
  devicesById: Map<number, ApiDevice>,
): Employee {
  const device = employee.device_id === null ? null : devicesById.get(employee.device_id) ?? null;
  return {
    id: `EMP-${String(employee.user_id).padStart(3, "0")}`,
    name: employee.name,
    email: employee.email,
    device: employee.device_name ?? NO_DEVICE_LABEL,
    status: employee.device_status === "ONLINE" ? "Online" : "Offline",
    tasks: employee.active_tasks,
    os: device?.os ?? "—",
    agentVersion: device?.agent_version ?? "—",
    lastSeen: relativeTime(employee.last_heartbeat_at),
    activeTaskId: undefined,
    recentActivity: [],
    errors: device && device.status !== "ONLINE" ? ["Device tidak mengirim heartbeat."] : [],
  };
}

function mapEmployeeDetail(detail: ApiEmployeeDetail, base: Employee | null): Employee {
  return {
    id: base?.id ?? `EMP-${String(detail.user_id).padStart(3, "0")}`,
    name: detail.name,
    email: detail.email,
    device: detail.device_name ?? NO_DEVICE_LABEL,
    status: detail.device_status === "ONLINE" ? "Online" : "Offline",
    tasks: detail.tasks.length,
    os: detail.os ?? "—",
    agentVersion: detail.agent_version ?? "—",
    lastSeen: relativeTime(detail.last_heartbeat_at),
    activeTaskId: undefined,
    recentActivity: detail.recent_activity.map(
      (row) => `${row.actor ?? "Sistem"} ${ACTION_LABEL[row.action] ?? row.action}`,
    ),
    errors: detail.device_status && detail.device_status !== "ONLINE"
      ? ["Device tidak mengirim heartbeat."]
      : [],
  };
}

function mapDevice(device: ApiDevice): Device {
  return {
    id: `DEV-${String(device.id).padStart(3, "0")}`,
    name: device.device_name,
    os: device.os ?? "—",
    agentVersion: device.agent_version ?? "—",
    status: connectionStatus(device),
    lastHeartbeat: relativeTime(device.last_heartbeat_at),
    owner: device.user_name ?? "—",
    ownerEmail: "",
    activeTaskId: device.current_task ? `TASK-${device.current_task.id}` : undefined,
    capabilities: device.capabilities,
  };
}

function mapApproval(
  approval: Approval,
  users: Map<number, string>,
  devicesByUser: Map<number, string>,
): ApprovalRequest {
  return {
    id: `APR-${String(approval.id).padStart(3, "0")}`,
    user: users.get(approval.user_id) ?? `User #${approval.user_id}`,
    action: approval.action,
    reason: approval.risk ?? "Diminta melalui RAPIIN.",
    scope: approval.scope ?? "—",
    risk: approval.risk ?? "—",
    requested: clockTime(approval.created_at),
    device: devicesByUser.get(approval.user_id) ?? "—",
    status:
      approval.status === "APPROVED"
        ? "Approved"
        : approval.status === "REJECTED"
          ? "Rejected"
          : "Pending",
    destructive: approval.tool_name ? DESTRUCTIVE_TOOLS.has(approval.tool_name) : false,
  };
}

interface OpsState {
  overview: {
    status: string;
    frozen: boolean;
    freezeReason: string | null;
    activeIncidents: number;
    criticalCount: number;
    pendingApprovals: number;
  } | null;
  incidents: OpsIncident[];
  agents: OpsAgent[];
  approvals: OpsApproval[];
}

export interface SupervisorDataValue {
  loading: boolean;
  error: string | null;
  overview: SupervisorOverview | null;
  tasks: SupervisorTask[];
  employees: Employee[];
  devices: Device[];
  approvals: ApprovalRequest[];
  activity: ActivityEvent[];
  policies: ActionPolicy[];
  profile: Profile | null;
  accounts: SupervisorAccounts | null;
  ops: OpsState;
  refresh: () => void;
  loadTask: (taskId: number) => Promise<SupervisorTask | null>;
  loadEmployee: (userId: number, base: Employee) => Promise<Employee | null>;
  respondApproval: (displayId: string, status: Exclude<ApprovalStatus, "Pending">) => Promise<void>;
  refreshOps: () => void;
  dispatchIncident: (displayId: string) => Promise<void>;
  setFreeze: (enabled: boolean, reason: string) => Promise<void>;
  respondOpsApproval: (
    displayId: string,
    decision: "APPROVED" | "REJECTED",
    password: string,
  ) => Promise<void>;
  updatePolicy: (toolName: string, approvalKind: string, bulkThreshold: number) => Promise<void>;
  setEmployeeActive: (userId: number, isActive: boolean) => Promise<void>;
  logout: () => void;
}

const SupervisorDataContext = createContext<SupervisorDataValue | null>(null);

export function useSupervisorData(): SupervisorDataValue {
  const value = useContext(SupervisorDataContext);
  if (!value) throw new Error("useSupervisorData must be used within SupervisorDataProvider");
  return value;
}

const EMPTY_OPS: OpsState = {
  overview: null,
  incidents: [],
  agents: [],
  approvals: [],
};

/** Display ids keep their notation ("APR-021"); the API needs the numeric part. */
function numericId(displayId: string): number | null {
  const digits = displayId.replace(/[^0-9]/g, "");
  if (!digits) return null;
  const value = Number(digits);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function SupervisorDataProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<SupervisorOverview | null>(null);
  const [tasks, setTasks] = useState<SupervisorTask[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [policies, setPolicies] = useState<ActionPolicy[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [accounts, setAccounts] = useState<SupervisorAccounts | null>(null);
  const [ops, setOps] = useState<OpsState>(EMPTY_OPS);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const [ov, apiDevices, apiEmployees, apiTasks, apiApprovals, apiActivity, apiPolicies, me, accts] =
          await Promise.all([
            apiGet<SupervisorOverview>("/supervisor/overview"),
            apiGet<ApiDevice[]>("/supervisor/devices"),
            apiGet<ApiEmployee[]>("/supervisor/employees"),
            apiGet<ApiTask[]>("/supervisor/tasks"),
            apiGet<Approval[]>("/supervisor/approvals?include_decided=true"),
            apiGet<AuditEvent[]>("/supervisor/activity"),
            apiGet<ActionPolicy[]>("/supervisor/policies"),
            apiGet<Profile>("/supervisor/profile").catch(() => null),
            apiGet<SupervisorAccounts>("/supervisor/accounts").catch(() => null),
          ]);

        if (cancelled) return;

        const users = new Map<number, string>();
        const devicesById = new Map<number, ApiDevice>();
        const devicesByUser = new Map<number, string>();
        for (const employee of apiEmployees) {
          users.set(employee.user_id, employee.name);
        }
        for (const device of apiDevices) {
          devicesById.set(device.id, device);
          if (device.user_id !== undefined) devicesByUser.set(device.user_id, device.device_name);
        }
        for (const task of apiTasks) {
          if (!users.has(task.user_id)) users.set(task.user_id, `User #${task.user_id}`);
        }

        setOverview(ov);
        setDevices(apiDevices.map(mapDevice));
        setEmployees(apiEmployees.map((employee) => mapEmployee(employee, devicesById)));
        setTasks(apiTasks.map((task) => mapTask(task, users, devicesByUser)));
        setApprovals(apiApprovals.map((item) => mapApproval(item, users, devicesByUser)));
        setActivity(mapActivity(apiActivity));
        setPolicies(apiPolicies);
        setProfile(me);
        setAccounts(accts);
        setError(null);
      } catch (cause) {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Gagal memuat data supervisor.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  const loadTask = useCallback(async (taskId: number) => {
    try {
      const task = await apiGet<ApiTask>(`/supervisor/tasks/${taskId}`);
      return mapTask(task, new Map(), new Map());
    } catch {
      return null;
    }
  }, []);

  const loadEmployee = useCallback(
    async (userId: number, base: Employee) => {
      try {
        const detail = await apiGet<ApiEmployeeDetail>(`/supervisor/employees/${userId}`);
        return mapEmployeeDetail(detail, base);
      } catch {
        return null;
      }
    },
    [],
  );

  const respondApproval = useCallback(
    async (displayId: string, status: Exclude<ApprovalStatus, "Pending">) => {
      const id = numericId(displayId);
      if (id === null) return;
      await apiPost(`/supervisor/approvals/${id}/respond`, {
        decision: status === "Approved" ? "APPROVED" : "REJECTED",
      });
      refresh();
    },
    [refresh],
  );

  const loadOps = useCallback(async () => {
    try {
      const [ov, apiIncidents, apiAgents, apiApprovals] = await Promise.all([
        apiGet<{
          status: string;
          freeze: { enabled: boolean; reason: string | null };
          active_incidents: number;
          severity_counts: Record<string, number>;
          pending_approvals: number;
          agents: Array<Record<string, unknown>>;
        }>("/supervisor/ops/overview"),
        apiGet<Array<Record<string, unknown>>>("/supervisor/ops/incidents"),
        apiGet<Array<Record<string, unknown>>>("/supervisor/ops/agents"),
        apiGet<Array<Record<string, unknown>>>("/supervisor/ops/approvals"),
      ]);

      const pending = apiApprovals.filter((row) => row.status === "PENDING");
      const incidentsById = new Map<number, Record<string, unknown>>();
      const proposalsById = new Map<number, Record<string, unknown>>();
      for (const incident of apiIncidents) incidentsById.set(Number(incident.id), incident);

      // Approval rows carry no title/description, so read them from the linked proposal.
      await Promise.all(
        pending.map(async (row) => {
          const incidentId = Number(row.incident_id);
          if (!incidentsById.has(incidentId)) return;
          try {
            const detail = await apiGet<{
              proposals?: Array<Record<string, unknown>>;
            }>(`/supervisor/ops/incidents/${incidentId}`);
            for (const proposal of detail.proposals ?? []) {
              proposalsById.set(Number(proposal.id), proposal);
            }
          } catch {
            // Approval renders with fallback copy when the proposal is unavailable.
          }
        }),
      );

      setOps({
        overview: {
          status: ov.status,
          frozen: Boolean(ov.freeze?.enabled),
          freezeReason: ov.freeze?.reason ?? null,
          activeIncidents: ov.active_incidents,
          criticalCount: ov.severity_counts?.CRITICAL ?? 0,
          pendingApprovals: ov.pending_approvals,
        },
        incidents: apiIncidents.map((row) => {
          const id = Number(row.id);
          return {
            id: `OPS-${id}`,
            title: String(row.title ?? ""),
            severity: String(row.severity ?? "LOW") as OpsSeverity,
            status: String(row.status ?? "OPEN") as OpsIncidentStatus,
            source: String(row.source ?? ""),
            resource: String(row.affected_resource ?? "—"),
            summary: String(row.summary ?? ""),
            occurrences: Number(row.occurrence_count ?? 1),
            firstSeen: relativeTime(String(row.first_seen_at ?? "")),
            lastSeen: relativeTime(String(row.last_seen_at ?? "")),
            assigned: [],
            timeline: [],
          };
        }),
        agents: apiAgents.map((row) => {
          const role = String(row.role ?? "LEAD") as OpsAgentRole;
          const toolPolicy = (() => {
            try {
              return JSON.parse(String(row.tool_policy ?? "{}")) as {
                allowed_tools?: string[];
                read_only?: boolean;
                may_change_code?: boolean;
                may_deploy?: boolean;
              };
            } catch {
              return {};
            }
          })();
          return {
            role,
            purpose: OPS_AGENT_PURPOSE[role] ?? role,
            tools: toolPolicy.allowed_tools ?? [],
            boundary: toolPolicy.may_deploy
              ? "Boleh deploy setelah approval terpisah."
              : toolPolicy.may_change_code
                ? "Hanya worktree terisolasi. Fix butuh approval supervisor."
                : "Read-only. Tanpa mutasi apa pun.",
            state: String(row.state ?? "IDLE") === "RUNNING" ? "ACTIVE" : "IDLE",
          } satisfies OpsAgent;
        }),
        approvals: apiApprovals
          .filter((row) => row.status === "PENDING" || row.status === "APPROVED" || row.status === "REJECTED")
          .map((row) => {
            const incidentId = Number(row.incident_id);
            const proposal = proposalsById.get(Number(row.proposal_id));
            return {
              id: `OPS-APR-${row.id}`,
              incidentId: `OPS-${incidentId}`,
              kind: String(row.approval_type ?? "CODE_FIX") as OpsApproval["kind"],
              title: String(proposal?.title ?? proposalsById.get(Number(row.proposal_id))?.title ?? "Perubahan operasi"),
              description: String(proposal?.description ?? "Detail proposal tersedia di halaman insiden."),
              risk: String(proposal?.risk ?? "Perubahan pada sistem operasi."),
              status:
                row.status === "APPROVED"
                  ? "Approved"
                  : row.status === "REJECTED" || row.status === "EXPIRED"
                    ? "Rejected"
                    : "Pending",
              requested: clockTime(String(row.requested_at ?? "")),
            } satisfies OpsApproval;
          }),
      });
    } catch {
      setOps(EMPTY_OPS);
    }
  }, []);

  useEffect(() => {
    void loadOps();
  }, [loadOps, reloadToken]);

  const refreshOps = useCallback(() => setReloadToken((token) => token + 1), []);

  const dispatchIncident = useCallback(
    async (displayId: string) => {
      const id = numericId(displayId);
      if (id === null) return;
      await apiPost(`/supervisor/ops/incidents/${id}/agents/dispatch`);
      refreshOps();
    },
    [refreshOps],
  );

  const setFreeze = useCallback(
    async (enabled: boolean, reason: string) => {
      await apiPost("/supervisor/ops/emergency-pause", { enabled, reason });
      refreshOps();
    },
    [refreshOps],
  );

  const respondOpsApproval = useCallback(
    async (displayId: string, decision: "APPROVED" | "REJECTED", password: string) => {
      const id = numericId(displayId);
      if (id === null) return;
      await apiPost(`/supervisor/ops/approvals/${id}/respond`, {
        decision,
        note: "",
        ...(decision === "APPROVED" ? { password } : {}),
      });
      refreshOps();
    },
    [refreshOps],
  );

  const updatePolicy = useCallback(
    async (toolName: string, approvalKind: string, bulkThreshold: number) => {
      await apiPut(`/supervisor/policies/${toolName}`, {
        approval_kind: approvalKind,
        bulk_threshold: bulkThreshold,
      });
      refresh();
    },
    [refresh],
  );

  const setEmployeeActive = useCallback(
    async (userId: number, isActive: boolean) => {
      await apiPatch(`/supervisor/employees/${userId}/state`, { is_active: isActive });
      refresh();
    },
    [refresh],
  );

  const logout = useCallback(() => {
    apiPost("/auth/logout").catch(() => undefined);
    clearSession();
    window.location.assign("/login");
  }, []);

  const value = useMemo<SupervisorDataValue>(
    () => ({
      loading,
      error,
      overview,
      tasks,
      employees,
      devices,
      approvals,
      activity,
      policies,
      profile,
      accounts,
      ops,
      refresh,
      loadTask,
      loadEmployee,
      respondApproval,
      refreshOps,
      dispatchIncident,
      setFreeze,
      respondOpsApproval,
      updatePolicy,
      setEmployeeActive,
      logout,
    }),
    [
      accounts,
      activity,
      approvals,
      devices,
      dispatchIncident,
      employees,
      error,
      loadEmployee,
      loadTask,
      loading,
      logout,
      ops,
      overview,
      policies,
      profile,
      refresh,
      refreshOps,
      respondApproval,
      respondOpsApproval,
      setEmployeeActive,
      setFreeze,
      tasks,
      updatePolicy,
    ],
  );

  return (
    <SupervisorDataContext.Provider value={value}>{children}</SupervisorDataContext.Provider>
  );
}

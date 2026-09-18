export type SupervisorPage =
  | "overview"
  | "tasks"
  | "employees"
  | "devices"
  | "approvals"
  | "activity"
  | "operations"
  | "settings"
  | "account";

export type TaskStatus =
  | "Running"
  | "Waiting"
  | "Completed"
  | "Failed";

export type EmployeeStatus = "Online" | "Offline" | "Warning";
export type ApprovalStatus = "Pending" | "Approved" | "Rejected";
export type ActivityTone = "success" | "warning" | "danger" | "info";

export interface SupervisorTask {
  id: string;
  user: string;
  title: string;
  status: TaskStatus;
  progress: number | null;
  processed: number;
  total: number;
  device: string;
  started: string;
  updated: string;
  error?: string;
  activity: Array<{
    label: string;
    state: "complete" | "current" | "pending" | "failed";
  }>;
}

export interface Employee {
  id: string;
  name: string;
  email: string;
  device: string;
  status: EmployeeStatus;
  tasks: number | null;
  os: string;
  agentVersion: string;
  lastSeen: string;
  activeTaskId?: string;
  recentActivity: string[];
  errors: string[];
}

export interface Device {
  id: string;
  name: string;
  os: string;
  agentVersion: string;
  status: EmployeeStatus;
  lastHeartbeat: string;
  owner: string;
  ownerEmail: string;
  activeTaskId?: string;
  capabilities: string[];
}

export interface ApprovalRequest {
  id: string;
  user: string;
  action: string;
  reason: string;
  scope: string;
  risk: string;
  requested: string;
  device: string;
  status: ApprovalStatus;
  destructive: boolean;
}

export interface ActivityEvent {
  id: string;
  time: string;
  title: string;
  detail?: string;
  tone: ActivityTone;
  category: "Task" | "Approval" | "Device" | "Account";
  actor: string;
  device?: string;
  taskId?: string;
}

export type OpsSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type OpsIncidentStatus =
  | "OPEN"
  | "INVESTIGATING"
  | "AWAITING_APPROVAL"
  | "APPROVED_FOR_FIX"
  | "FIXING"
  | "VERIFYING"
  | "AWAITING_DEPLOY_APPROVAL"
  | "DEPLOYING"
  | "RESOLVED"
  | "REJECTED";

export type OpsAgentRole = "LEAD" | "SECURITY" | "DIAGNOSTIC" | "CODER";
export type OpsAgentState = "IDLE" | "ACTIVE";

export interface OpsIncidentEvent {
  time: string;
  label: string;
  actor: string;
}

export interface OpsIncident {
  id: string;
  title: string;
  severity: OpsSeverity;
  status: OpsIncidentStatus;
  source: string;
  resource: string;
  summary: string;
  occurrences: number;
  firstSeen: string;
  lastSeen: string;
  assigned: OpsAgentRole[];
  timeline: OpsIncidentEvent[];
}

export interface OpsApproval {
  id: string;
  incidentId: string;
  kind: "CODE_FIX" | "DEPLOYMENT";
  title: string;
  description: string;
  risk: string;
  status: ApprovalStatus;
  requested: string;
}

export interface OpsAgent {
  role: OpsAgentRole;
  purpose: string;
  tools: string[];
  boundary: string;
  state: OpsAgentState;
}

export const pageTitles: Record<SupervisorPage, string> = {
  overview: "Ringkasan",
  tasks: "Tugas",
  employees: "Pegawai",
  devices: "Perangkat",
  approvals: "Persetujuan",
  activity: "Aktivitas",
  operations: "Operasi",
  settings: "Pengaturan",
  account: "Akun Supervisor",
};

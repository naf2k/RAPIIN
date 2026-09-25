export type Role = "USER" | "SUPERVISOR";

export type TaskStatus =
  | "PENDING"
  | "PLANNING"
  | "WAITING_APPROVAL"
  | "RUNNING"
  | "VERIFYING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type DeviceStatus = "ONLINE" | "OFFLINE";
export type ConnectionHealth = "HEALTHY" | "DEGRADED" | "OFFLINE";
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED";
export type ApprovalKind = "USER" | "SUPERVISOR";
export type PolicyKind = "AUTO" | "USER" | "SUPERVISOR";
export type NotificationType = "info" | "success" | "error" | "warning";

export interface TaskActivity {
  id: number;
  actor: string | null;
  actor_role: string | null;
  action: string;
  resource: string | null;
  timestamp: string;
  result: string;
  error: string | null;
}

export interface Task {
  id: number;
  user_id: number;
  device_id: number | null;
  type: string;
  status: TaskStatus;
  progress: number;
  processed_count: number;
  total_count: number;
  cancel_requested: number;
  result_json: string | null;
  error: string | null;
  approval_status: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  activity?: TaskActivity[];
}

export interface ToolEvent {
  tool: string;
  status: string;
  result?: unknown;
  error?: string;
  approval_id?: number;
}

export interface OrganizerRecommendation {
  id: string | number;
  kind?: string;
  title?: string;
  detail?: string;
  count?: number;
  apply?: { tool_name?: string; tool_args?: Record<string, unknown> };
}

export interface OrganizerResult {
  directory?: string;
  recommendations?: OrganizerRecommendation[];
}

export interface FileEntry {
  name: string;
  extension: string;
  size: number;
  modified: number;
}

/** Shape returned by the filesystem scanner / file search tools. */
export interface FileListing {
  directory: string;
  files: FileEntry[];
  folders: string[];
  fileCount: number;
  truncated: boolean;
  /** Set when the listing came from a search rather than a folder scan. */
  query?: string;
}

/** Shape of `tasks.result_json` once parsed. */
export interface TaskResult {
  tool_events?: ToolEvent[];
  tool_result?: unknown;
  final_response?: string;
}

export interface Approval {
  id: number;
  task_id: number | null;
  user_id: number;
  requested_by: string;
  kind: ApprovalKind;
  action: string;
  scope: string | null;
  risk: string | null;
  tool_name: string | null;
  tool_args: string | null;
  snapshot_hash: string | null;
  expires_at: string | null;
  status: ApprovalStatus;
  decided_by: number | null;
  decided_at: string | null;
  created_at: string;
  user_name?: string;
}

export interface CurrentTaskRef {
  id: number;
  type: string;
  status: TaskStatus;
  progress: number;
}

export interface Device {
  id: number;
  device_name: string;
  os: string | null;
  agent_version: string | null;
  status: DeviceStatus;
  last_heartbeat_at: string | null;
  capabilities: string[];
  workspace_root: string | null;
  allowed_roots: string[];
  heartbeat_age_seconds: number | null;
  connection_health: ConnectionHealth;
  current_task: CurrentTaskRef | null;
  user_name?: string;
  user_id?: number;
}

export interface Conversation {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: string;
  content: string;
  tool_name: string | null;
  created_at: string;
}

export interface Notification {
  id: number;
  title: string;
  body: string | null;
  type: NotificationType;
  is_read: number;
  created_at: string;
  task_id: number | null;
}

export interface Employee {
  user_id: number;
  name: string;
  email: string;
  is_active: number;
  device_id: number | null;
  device_name: string | null;
  device_status: DeviceStatus | null;
  last_heartbeat_at: string | null;
  active_tasks: number;
}

export interface EmployeeDetail {
  user_id: number;
  name: string;
  email: string;
  is_active: number;
  created_at: string;
  device_id: number | null;
  device_name: string | null;
  os: string | null;
  agent_version: string | null;
  device_status: DeviceStatus | null;
  last_heartbeat_at: string | null;
  tasks: Task[];
  recent_activity: TaskActivity[];
}

export interface AuditEvent {
  id: number;
  actor: string | null;
  actor_role: string | null;
  user_id: number | null;
  device_id: number | null;
  action: string;
  resource: string | null;
  timestamp: string;
  result: string;
  error: string | null;
  approval_id: number | null;
  task_id: number | null;
}

export interface AttentionItem {
  type: string;
  title: string;
  detail: string;
  link: string;
}

export interface SupervisorOverview {
  status: "SEHAT" | "PERLU_PERHATIAN" | string;
  active_users: number;
  running_tasks: number;
  waiting_approvals: number;
  success_rate: number | null;
  failed_tasks: number;
  attention: AttentionItem[];
  recent_activity: AuditEvent[];
}

export interface Profile {
  id: number;
  name: string;
  email: string;
  role: Role;
}

export interface SupervisorAccount {
  id: number;
  name: string;
  email: string;
  is_active: number;
  created_at: string;
}

export interface SupervisorAccounts {
  count: number;
  max: number;
  accounts: SupervisorAccount[];
}

export interface ActionPolicy {
  tool_name: string;
  approval_kind: PolicyKind;
  bulk_threshold: number;
}

export interface LoginResponse {
  token: string;
  user_id: number;
  name: string;
  role: Role;
}

export interface RegisterResponse {
  token: string;
  user_id: number;
  device: {
    device_id: number;
    device_key: string;
  };
}

export interface CreateConversationResponse {
  conversation_id: number;
  title: string;
}

export interface SendMessageResponse {
  reply: null;
  task_id: number;
  status: string;
  message: string;
}

export interface ApplyRecommendationResponse {
  approval_id: number;
  task_id: number;
  status: string;
  action: string;
  tool: string;
  file_count: number;
}

export type UserSettings = Record<string, string>;

export interface SupervisorNotifications {
  items: Notification[];
  unread: number;
}

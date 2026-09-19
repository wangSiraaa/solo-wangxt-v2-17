export interface Dataset {
  id: string;
  name: string;
  description: string;
  record_count: number;
  participant_count: number;
}

export interface Purpose {
  code: string;
  name: string;
  description: string;
}

export interface GrantInfo {
  id: number;
  expires_at: string;
  granted_by?: string;
}

export interface AccessRequest {
  id: number;
  researcher_id: string;
  researcher_name?: string;
  project_title: string;
  dataset_id: string;
  purpose_code: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
  decision_note: string | null;
  grant: GrantInfo | null;
}

export interface ExportInfo {
  id: number;
  grant_id: number;
  dataset_id: string;
  purpose_code: string;
  status: "queued" | "running" | "completed" | "cancelled" | "failed";
  cancel_reason: string | null;
  row_count: number | null;
  created_at: string;
  finished_at: string | null;
  downloaded: boolean;
  download_token: string | null;
  link_expires_at: string | null;
}

export interface AccessEvent {
  id: number;
  actor_id: string;
  actor_role: string;
  event_type: string;
  request_id: number | null;
  grant_id: number | null;
  export_job_id: number | null;
  participant_id: string | null;
  purpose_code: string | null;
  dataset_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface ProjectInfo {
  grant_id: number;
  project_title: string;
  researcher_name: string;
  dataset_id: string;
  grant_expires_at: string;
  exports: { id: number; status: string; downloaded: boolean }[];
}

export interface PurposeOverview {
  code: string;
  name: string;
  description: string;
  status: "granted" | "withdrawn" | "none";
  version: number;
  updated_at: string | null;
  datasets: string[];
  projects: ProjectInfo[];
  withdrawal_impact: { queued_exports: number; active_download_links: number };
}

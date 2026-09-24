import { appConfig } from "./config";

export type ApiHealth = {
  status: string;
  app_name: string;
  environment: string;
};

export async function fetchHealth(): Promise<ApiHealth> {
  const response = await fetch(`${appConfig.apiBaseUrl}/health`);

  if (!response.ok) {
    throw new Error("Backend health request failed.");
  }

  return response.json() as Promise<ApiHealth>;
}

export type EvidenceReference = {
  observation_id: string;
  evidence_id: string;
  source_name: string;
  source_type: string;
  source_timestamp: string;
  status: string;
  progress: number | null;
  weight: number;
  reliability_score?: number;
  freshness_score?: number;
  is_stale?: boolean;
  is_duplicate?: boolean;
  contradiction_reason?: string | null;
};

export type DependencyValidationDetail = {
  predecessor_activity_id: string | null;
  predecessor_activity_name: string | null;
  successor_activity_id: string | null;
  successor_activity_name: string | null;
  relevant_actual_start: string | null;
  relevant_actual_end: string | null;
  rule: string | null;
  status: "VALID" | "WARNING" | "CONFLICT" | "UNKNOWN" | string;
  reason: string | null;
};

export type PlannerReviewContext = {
  review_id: string;
  reviewer?: string | null;
  reviewer_decision: string;
  reviewer_comment: string | null;
  reason: string;
  current_activity: { activity_id: string; external_activity_id: string; description: string; status: string; actual_progress: number | null; actual_start: string | null; actual_end: string | null };
  proposed_reconciliation: {
    confidence: number;
    reconciled_status: string;
    reconciled_progress: number | null;
    explanation: string;
    recommended_action: string;
    decision: string;
    dependency_status?: string | null;
    dependency_details?: DependencyValidationDetail[];
  };
  supporting_evidence: EvidenceReference[];
  conflicting_evidence: EvidenceReference[];
  match_candidates: { activity_id: string; external_activity_id: string; description: string; final_score: number; explanation: string }[];
  audit_history: { audit_id: string; action: string; actor: string; explanation: string | null; created_at: string }[];
};

export async function fetchPlannerReviews(projectId: string): Promise<PlannerReviewContext[]> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/planner-reviews`);
  if (!response.ok) throw new Error("Unable to load planner reviews.");
  return response.json() as Promise<PlannerReviewContext[]>;
}

export async function actOnPlannerReview(projectId: string, reviewId: string, payload: Record<string, unknown>): Promise<PlannerReviewContext> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/planner-reviews/${reviewId}/actions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Planner action was not accepted.");
  return response.json() as Promise<PlannerReviewContext>;
}

export type DashboardData = {
  overview: Record<string, number>;
  activities: Array<Record<string, any>>;
  reconciliations: Array<Record<string, any>>;
  conflicts: Array<Record<string, any>>;
  evidence: Array<Record<string, any>>;
  audit_trail: Array<Record<string, any>>;
  pipeline: Array<Record<string, any>>;
};

export async function fetchDashboard(projectId: string): Promise<DashboardData> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/dashboard`);
  if (!response.ok) throw new Error("Unable to load project dashboard.");
  return response.json() as Promise<DashboardData>;
}

export async function resetDemo(): Promise<{ project_id: string; project_name: string }> {
  const response = await fetch(`${appConfig.apiBaseUrl}/demo/reset`, { method: "POST" });
  if (!response.ok) throw new Error("Unable to reset the project baseline.");
  return response.json();
}

export type ExtractedEventItem = {
  observation_id: string;
  evidence_id: string;
  activity_description: string;
  discipline: string | null;
  location: string | null;
  status: string;
  progress: number | null;
  actual_start: string | null;
  actual_end: string | null;
  confidence: number;
  notes?: string | null;
  contractor?: string | null;
  equipment_or_tag?: string | null;
};

export type PipelineProgressResult = {
  status: string;
  evidence_count: number;
  observations_extracted: number;
  matched_count: number;
  reconciled_count: number;
  extracted_events: ExtractedEventItem[];
};

export async function pasteDprReport(
  projectId: string,
  rawText: string,
  sourceName = "pasted_field_report.txt",
  sourceType = "daily_report",
  autoExtract = true
): Promise<PipelineProgressResult> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/imports/paste`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      raw_text: rawText,
      source_name: sourceName,
      source_type: sourceType,
      auto_extract: autoExtract,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to ingest pasted field report.");
  }
  return response.json() as Promise<PipelineProgressResult>;
}

export async function uploadEvidenceFile(
  projectId: string,
  file: File,
  sourceType: string
): Promise<{ status: string; records_imported: number }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("source_type", sourceType);
  formData.append("auto_extract", "true");

  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/imports/evidence`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload evidence file.");
  }
  return response.json();
}

export async function continueToMatchingAndReconciliation(
  projectId: string
): Promise<PipelineProgressResult> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/imports/process-pipeline`, {
    method: "POST",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to process matching and reconciliation pipeline.");
  }
  return response.json() as Promise<PipelineProgressResult>;
}

export type DependencyContext = {
  dependency_id: string;
  activity_id: string;
  external_activity_id: string;
  description: string;
  dependency_type: string;
  lag_days: number;
  status: string;
  progress: number | null;
  actual_start: string | null;
  actual_end: string | null;
  planned_start: string | null;
  planned_finish: string | null;
};

export type CandidateActivityMatch = {
  activity_id: string;
  external_activity_id: string;
  description: string;
  similarity_score: number;
  contextual_score: number;
  final_score: number;
  explanation: string;
};

export type ExecutionEventContext = {
  event_id: string;
  evidence_id: string;
  source_name: string;
  source_type: string;
  source_timestamp: string;
  field_description: string;
  discipline: string | null;
  location: string | null;
  contractor: string | null;
  status: string;
  progress: number | null;
  actual_start: string | null;
  actual_end: string | null;
  extraction_confidence: number;
  match_score: number | null;
  match_outcome: string | null;
  candidates: CandidateActivityMatch[];
  reconciliation_decision: string | null;
  is_supporting: boolean;
  is_conflicting: boolean;
};

export type ProvenanceTrace = {
  field: string;
  value: string;
  event_id: string;
  evidence_id: string;
  source_name: string;
  source_type: string;
  source_timestamp: string;
  contractor: string | null;
  rationale: string;
};

export type ReconciliationSummary = {
  reconciliation_id: string;
  decision: string;
  status: string;
  progress: number | null;
  confidence: number;
  explanation: string;
  created_at: string;
};

export type TemporalValidationSummary = {
  is_valid: boolean;
  status: string;
  rule_name: string | null;
  details: string | null;
};

export type ExecutionContextResponse = {
  activity: {
    activity_id: string;
    external_activity_id: string;
    discipline: string | null;
    description: string;
    location: string | null;
    planned_start: string | null;
    planned_finish: string | null;
    actual_start: string | null;
    actual_end: string | null;
    progress: number | null;
    status: string;
    level: number;
  };
  predecessors: DependencyContext[];
  successors: DependencyContext[];
  execution_events: ExecutionEventContext[];
  reconciliation: ReconciliationSummary | null;
  temporal_validation: TemporalValidationSummary;
  provenance: ProvenanceTrace[];
};

export async function fetchExecutionContext(
  projectId: string,
  activityId: string
): Promise<ExecutionContextResponse> {
  const response = await fetch(
    `${appConfig.apiBaseUrl}/projects/${projectId}/activities/${activityId}/execution-context`
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Unable to load activity execution context.");
  }
  return response.json() as Promise<ExecutionContextResponse>;
}

export type ScheduleChangeItem = {
  activity_id: string;
  external_activity_id: string;
  activity_name: string;
  discipline: string | null;
  location: string | null;
  field: string;
  old_value: string;
  new_value: string;
  source_evidence: string;
  match_confidence: number | null;
  reconciliation_confidence: number | null;
  temporal_status: string;
  decision: "VERIFIED" | "PLANNER_REVIEW" | "CONFLICT" | "REJECTED" | "UNCHANGED";
  decision_source: string;
  rationale: string;
  updated_at: string | null;
};

export type ScheduleExportSummary = {
  activities_evaluated: number;
  verified_updates: number;
  planner_review: number;
  conflicts: number;
  rejected: number;
  unchanged: number;
};

export type ScheduleChangePreviewResponse = {
  project_id: string;
  summary: ScheduleExportSummary;
  changes: ScheduleChangeItem[];
  deferral_notice: string;
};

export async function fetchSchedulePreview(projectId: string): Promise<ScheduleChangePreviewResponse> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/schedule/preview`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Unable to load schedule change preview.");
  }
  return response.json() as Promise<ScheduleChangePreviewResponse>;
}

export async function downloadScheduleExport(projectId: string, format: "csv" | "xlsx"): Promise<void> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/schedule/export?format=${format}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to export schedule in ${format.toUpperCase()} format.`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  let filename = `verified_schedule.${format}`;
  if (disposition && disposition.includes("filename=")) {
    const match = disposition.match(/filename="?([^";]+)"?/);
    if (match && match[1]) filename = match[1];
  }
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function uploadScheduleFile(
  projectId: string,
  file: File,
  version: string
): Promise<{ status: string; records_imported: number }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("version", version);

  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/imports/schedule`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload schedule file.");
  }
  return response.json();
}

export type ExecutionDeviationItem = {
  deviation_id: string;
  deviation_type: string;
  metric_days: number | null;
  description: string;
};

export type ExecutionRecordResponse = {
  record_id: string;
  project_id: string;
  activity_id: string;
  external_activity_id: string;
  activity_name: string;
  discipline: string | null;
  contractor: string | null;
  location: string | null;
  planned_start: string | null;
  planned_finish: string | null;
  actual_start: string | null;
  actual_end: string | null;
  planned_duration_days: number | null;
  actual_duration_days: number | null;
  variance_days: number | null;
  status: string;
  percent_complete: number | null;
  reconciliation_decision: string | null;
  confidence: number | null;
  evidence_reference: string | null;
  source_timestamp: string | null;
  dependency_status: string | null;
  deviation_type: string;
  delay_cause: string | null;
  delay_category: string | null;
  delay_source_evidence: string | null;
  delay_confidence: number | null;
  planner_override: boolean;
  planner_notes: string | null;
  deviations: ExecutionDeviationItem[];
};

export type ActivityExecutionHistoryResponse = {
  activity_id: string;
  external_activity_id: string;
  activity_name: string;
  discipline: string | null;
  contractor: string | null;
  location: string | null;
  planned_start: string | null;
  planned_finish: string | null;
  actual_start: string | null;
  actual_end: string | null;
  planned_duration_days: number | null;
  actual_duration_days: number | null;
  variance_days: number | null;
  status: string;
  percent_complete: number | null;
  execution_evidence_citations: string[];
  recorded_deviations: string[];
  recorded_cause: string | null;
  delay_category: string | null;
  cause_source_reference: string | null;
  cause_confidence: number | null;
  planner_decisions: Array<{
    review_id: string;
    reviewer: string;
    proposed_decision: string;
    reviewer_decision: string;
    reviewer_comment: string | null;
    reviewed_at: string | null;
  }>;
};

export type DisciplinePerformanceItem = {
  discipline: string;
  total_activities: number;
  completed_activities: number;
  average_variance_days: number | null;
  delayed_count: number;
};

export type ContractorPerformanceItem = {
  contractor: string;
  total_activities: number;
  completed_activities: number;
  average_variance_days: number | null;
  delayed_count: number;
};

export type DelayCauseFrequencyItem = {
  category: string;
  count: number;
  sample_causes: string[];
};

export type ProjectPerformanceSummary = {
  project_id: string;
  project_name: string;
  total_activities: number;
  completed_activities: number;
  on_time_activities: number;
  late_activities: number;
  conflict_count: number;
  average_planned_duration_days: number | null;
  average_actual_duration_days: number | null;
  average_variance_days: number | null;
  top_delay_causes: DelayCauseFrequencyItem[];
  discipline_performance: DisciplinePerformanceItem[];
  contractor_performance: ContractorPerformanceItem[];
};

export type HistoricalReferenceItem = {
  activity_name: string;
  external_activity_id: string | null;
  project_name: string;
  discipline: string | null;
  contractor: string | null;
  planned_duration_days: number | null;
  actual_duration_days: number | null;
  variance_days: number | null;
  delay_cause: string | null;
  delay_category: string | null;
  evidence_reference: string | null;
  similarity_score: number;
  disclaimer: string;
};

export type SimilarExecutionSearchResponse = {
  query: string;
  discipline: string | null;
  results: HistoricalReferenceItem[];
  disclaimer: string;
};

export type CrossProjectMemoryResponse = {
  query_filter: string | null;
  discipline_filter: string | null;
  total_matching_records: number;
  completed_matching_records: number;
  average_variance_days: number | null;
  top_delay_causes: DelayCauseFrequencyItem[];
  discipline_breakdown: DisciplinePerformanceItem[];
  sample_records: HistoricalReferenceItem[];
  disclaimer: string;
};

export async function fetchProjectMemorySummary(projectId: string): Promise<ProjectPerformanceSummary> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/memory/summary`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch project execution memory summary.");
  }
  return response.json();
}

export async function fetchActivityExecutionHistory(
  projectId: string,
  activityId: string
): Promise<ActivityExecutionHistoryResponse> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/memory/activities/${activityId}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch activity execution history.");
  }
  return response.json();
}

export async function fetchProjectExecutionRecords(
  projectId: string,
  filters?: { discipline?: string; deviation_type?: string; contractor?: string }
): Promise<ExecutionRecordResponse[]> {
  const params = new URLSearchParams();
  if (filters?.discipline) params.append("discipline", filters.discipline);
  if (filters?.deviation_type) params.append("deviation_type", filters.deviation_type);
  if (filters?.contractor) params.append("contractor", filters.contractor);

  const url = `${appConfig.apiBaseUrl}/projects/${projectId}/memory/records${params.toString() ? `?${params.toString()}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch execution records.");
  }
  return response.json();
}

export async function fetchSimilarExecutions(
  projectId: string,
  query?: string,
  discipline?: string
): Promise<SimilarExecutionSearchResponse> {
  const params = new URLSearchParams();
  if (query) params.append("query", query);
  if (discipline) params.append("discipline", discipline);

  const url = `${appConfig.apiBaseUrl}/projects/${projectId}/memory/similar${params.toString() ? `?${params.toString()}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to find similar executions.");
  }
  return response.json();
}

export async function syncProjectMemory(projectId: string): Promise<ExecutionRecordResponse[]> {
  const response = await fetch(`${appConfig.apiBaseUrl}/projects/${projectId}/memory/sync`, {
    method: "POST",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to sync project execution memory.");
  }
  return response.json();
}




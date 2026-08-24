import type {AdvisoryResponse, CaseDetailResponse, CaseReplayTraceResponse, ContinuousIntelligenceStatus, DecisionBriefResponse, DecisionCockpitResponse, DemoSessionResponse, DeploymentIdentityResponse, EvaluationResponse, LiveStatusResponse, NarrationIntent, NarrationStatusResponse, OverviewResponse, PredictiveSnapshot, ReplayResponse} from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    const error = new Error(detail || `Request failed with ${response.status}`) as Error & {status?: number};
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<T>;
}

export const api = {
  deploymentIdentity: () => request<DeploymentIdentityResponse>("/api/deployment-identity"),
  liveStatus: () => request<LiveStatusResponse>("/api/live/status"),
  predictions: () => request<PredictiveSnapshot & {source: string}>("/api/predictions"),
  intelligenceStatus: () => request<ContinuousIntelligenceStatus>("/api/intelligence/status"),
  liveStreamUrl: () => `${API_BASE}/api/live/stream`,
  decisionCockpit: () => request<DecisionCockpitResponse>("/api/decision-cockpit"),
  decisionBrief: (caseId: string, audience: "manager" | "engineer") => request<DecisionBriefResponse>(`/api/cases/${caseId}/decision-brief?audience=${audience}`),
  demoSession: () => request<DemoSessionResponse>("/api/demo/session"),
  narrationStatus: () => request<NarrationStatusResponse>("/api/narration/status"),
  demoNarration: (sessionToken: string, caseId: string, audience: "manager" | "engineer", intent: NarrationIntent) => request<DecisionBriefResponse>("/api/demo/narration", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-FabOps-Demo-Session": sessionToken},
    body: JSON.stringify({case_id: caseId, audience, intent}),
  }),
  overview: () => request<OverviewResponse>("/api/overview"),
  caseDetail: (caseId: string) => request<CaseDetailResponse>(`/api/cases/${caseId}`),
  caseReplayTrace: (caseId: string) => request<CaseReplayTraceResponse>(`/api/cases/${caseId}/replay-trace`),
  advisory: (caseId: string) => request<AdvisoryResponse>(`/api/cases/${caseId}/advisory`),
  evaluation: () => request<EvaluationResponse>("/api/evaluation"),
  replay: () => request<ReplayResponse>("/api/replay"),
  requestEvidence: (caseId: string, reason: string) => request<{case: CaseDetailResponse["case"]}>(`/api/cases/${caseId}/request-evidence`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-FabOps-Role": "process_engineer", "X-FabOps-Actor": "workbench-engineer"},
    body: JSON.stringify({reason}),
  }),
  propose: (caseId: string, target: string, rationale: string) => request<{case: CaseDetailResponse["case"]}>(`/api/cases/${caseId}/actions/propose`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-FabOps-Role": "process_engineer", "X-FabOps-Actor": "workbench-engineer"},
    body: JSON.stringify({action_type: "diagnostic_inspection", target, rationale}),
  }),
  approve: (caseId: string, reason: string) => request<{case: CaseDetailResponse["case"]}>(`/api/cases/${caseId}/actions/approve`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-FabOps-Role": "yield_lead", "X-FabOps-Actor": "workbench-yield-lead"},
    body: JSON.stringify({reason}),
  }),
  reject: (caseId: string, reason: string) => request<{case: CaseDetailResponse["case"]}>(`/api/cases/${caseId}/actions/reject`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-FabOps-Role": "yield_lead", "X-FabOps-Actor": "workbench-yield-lead"},
    body: JSON.stringify({reason}),
  }),
};


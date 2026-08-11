import {useCallback, useEffect, useMemo, useState} from "react";
import {api} from "./api";
import {EvidenceInspector, WorkbenchState} from "./components";
import {DecisionApproval, EvaluationLab, EvidenceGraph, ExcursionCase, OperationsOverview, ReplayOperations, caseById} from "./screens";
import type {AdvisoryResponse, CaseDetailResponse, EvaluationResponse, OverviewResponse, ReplayResponse, ScreenId} from "./types";

const navigation: Array<{id: ScreenId; label: string; short: string}> = [
  {id: "overview", label: "Operations Overview", short: "OV"},
  {id: "case", label: "Excursion Case", short: "EC"},
  {id: "graph", label: "Evidence Graph", short: "EG"},
  {id: "decision", label: "Decision & Approval", short: "DA"},
  {id: "evaluation", label: "Evaluation Lab", short: "EL"},
  {id: "replay", label: "Replay & Operations", short: "RO"},
];

export default function App() {
  const [screen, setScreen] = useState<ScreenId>("overview");
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetailResponse | null>(null);
  const [advisory, setAdvisory] = useState<AdvisoryResponse | null>(null);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{kind: "ok" | "error" | "unauthorized"; message: string} | null>(null);

  const loadRoot = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextEvaluation, nextReplay] = await Promise.all([api.overview(), api.evaluation(), api.replay()]);
      setOverview(nextOverview);
      setEvaluation(nextEvaluation);
      setReplay(nextReplay);
      setSelectedCaseId((current) => current ?? nextOverview.cases[0]?.case_id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load workbench data");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCase = useCallback(async (caseId: string) => {
    try {
      const [nextDetail, nextAdvisory] = await Promise.all([api.caseDetail(caseId), api.advisory(caseId)]);
      setDetail(nextDetail);
      setAdvisory(nextAdvisory);
      setSelectedStep((current) => current && nextDetail.trace.process_path.some((item) => item.step_id === current) ? current : nextDetail.trace.process_path[0]?.step_id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load selected case");
    }
  }, []);

  useEffect(() => { void loadRoot(); }, [loadRoot]);
  useEffect(() => { if (selectedCaseId) void loadCase(selectedCaseId); }, [loadCase, selectedCaseId]);

  const selectedCase = useMemo(() => overview ? caseById(overview.cases, selectedCaseId) : null, [overview, selectedCaseId]);

  function selectCase(caseId: string) {
    setSelectedCaseId(caseId);
    setScreen("case");
    setFeedback(null);
  }

  async function mutate(action: () => Promise<unknown>) {
    if (!selectedCaseId) return;
    setBusy(true);
    setFeedback(null);
    try {
      await action();
      await Promise.all([loadRoot(), loadCase(selectedCaseId)]);
      setFeedback({kind: "ok", message: "The append-only workflow ledger and current case state were updated."});
    } catch (reason) {
      const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
      setFeedback({kind: status === 403 ? "unauthorized" : "error", message: reason instanceof Error ? reason.message : "Workflow action failed"});
    } finally {
      setBusy(false);
    }
  }

  if (loading && !overview) {
    return <main className="boot-state"><WorkbenchState kind="loading" title="Loading FabOps workbench" detail="Resolving source events, deterministic cases and projection freshness." /></main>;
  }
  if (error && !overview) {
    return <main className="boot-state"><WorkbenchState kind="error" title="Workbench unavailable" detail={error} action={<button onClick={() => void loadRoot()}>Retry</button>} /></main>;
  }
  if (!overview || !evaluation || !replay) {
    return <main className="boot-state"><WorkbenchState kind="empty" title="No operational evidence" detail="The API returned no source state." /></main>;
  }

  let workSurface;
  if (screen === "overview") workSurface = <OperationsOverview overview={overview} onSelectCase={selectCase} />;
  else if ((screen === "case" || screen === "graph" || screen === "decision") && !detail) workSurface = <WorkbenchState kind="loading" title="Loading selected case" detail="Fetching source-linked evidence and deterministic RCA." />;
  else if (screen === "case" && detail) workSurface = <ExcursionCase detail={detail} advisory={advisory} />;
  else if (screen === "graph" && detail) workSurface = <EvidenceGraph detail={detail} selectedStep={selectedStep} onSelectStep={setSelectedStep} />;
  else if (screen === "decision" && detail) workSurface = <DecisionApproval
    detail={detail}
    advisory={advisory}
    busy={busy}
    feedback={feedback}
    onRequestEvidence={(reason) => mutate(() => api.requestEvidence(detail.case.case_id, reason))}
    onPropose={(target, rationale) => mutate(() => api.propose(detail.case.case_id, target, rationale))}
    onApprove={(reason) => mutate(() => api.approve(detail.case.case_id, reason))}
    onReject={(reason) => mutate(() => api.reject(detail.case.case_id, reason))}
  />;
  else if (screen === "evaluation") workSurface = <EvaluationLab evaluation={evaluation} />;
  else workSurface = <ReplayOperations replay={replay} />;

  return <div className="app-shell">
    <header className="global-header">
      <div className="brand-mark">FDL</div>
      <div><strong>FabOps Decision Lab</strong><span>Evidence-Grounded Yield Excursion Triage</span></div>
      <div className="header-status">
        <span>RELEASE {replay.release.release_version}</span>
        <span>{replay.release.release_hash === "unreleased" ? "HASH PENDING" : replay.release.release_hash.slice(0, 12)}</span>
        <span>LLM OFF</span>
        <span>NO EQUIPMENT CONTROL</span>
      </div>
    </header>
    <aside className="left-rail" aria-label="Primary navigation">
      <div className="nav-heading"><span>Workbench</span><strong>Engineering decision</strong></div>
      <nav>{navigation.map((item) => <button key={item.id} className={screen === item.id ? "nav-item is-active" : "nav-item"} aria-current={screen === item.id ? "page" : undefined} onClick={() => setScreen(item.id)}>
        <span>{item.short}</span><strong>{item.label}</strong>
      </button>)}</nav>
      <div className="case-object-list">
        <span className="section-label">Case objects</span>
        {overview.cases.slice(0, 7).map((item) => <button key={item.case_id} className={item.case_id === selectedCaseId ? "case-object is-active" : "case-object"} onClick={() => selectCase(item.case_id)}>
          <span>{item.lot_id}</span><small>{item.classification.replaceAll("_", " ")}</small>
        </button>)}
      </div>
    </aside>
    <main id="work-surface" className="work-surface" tabIndex={-1}>{workSurface}</main>
    <EvidenceInspector selectedCase={detail?.case ?? selectedCase} projection={overview.projection} sourceTimestamp={overview.source_timestamp} selectedStep={selectedStep} />
  </div>;
}


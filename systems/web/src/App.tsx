import {useCallback, useEffect, useMemo, useState} from "react";
import {api} from "./api";
import {EvidenceInspector, WorkbenchState} from "./components";
import {DecisionApproval, DecisionCockpit, EvaluationLab, EvidenceGraph, ExcursionCase, OperationsOverview, ReplayOperations, caseById} from "./screens";
import type {AdvisoryResponse, CaseDetailResponse, DecisionBriefResponse, DecisionCockpitResponse, EvaluationResponse, NarrationIntent, NarrationStatusResponse, OverviewResponse, ReplayResponse, ScreenId} from "./types";

const navigation: Array<{id: ScreenId; label: string; short: string; group: "Decide" | "Investigate" | "Trust"}> = [
  {id: "cockpit", label: "Decision Cockpit", short: "01", group: "Decide"},
  {id: "decision", label: "Decision & Approval", short: "02", group: "Decide"},
  {id: "case", label: "Case Investigation", short: "03", group: "Investigate"},
  {id: "graph", label: "Evidence Graph", short: "04", group: "Investigate"},
  {id: "overview", label: "Operations Queue", short: "05", group: "Investigate"},
  {id: "evaluation", label: "Model & Evidence", short: "06", group: "Trust"},
  {id: "replay", label: "System Health", short: "07", group: "Trust"},
];

const screenPaths: Record<ScreenId, string> = {
  cockpit: "/DecisionCockpit",
  decision: "/DecisionApproval",
  case: "/CaseInvestigation",
  graph: "/EvidenceGraph",
  overview: "/OperationsQueue",
  evaluation: "/ModelEvidence",
  replay: "/SystemHealth",
};

function screenFromPath(pathname: string): ScreenId {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  const match = (Object.entries(screenPaths) as Array<[ScreenId, string]>).find(([, path]) => path.toLowerCase() === normalized.toLowerCase());
  return match?.[0] ?? "cockpit";
}

function InitialBoot() {
  return <main className="boot-experience" aria-label="Loading FabOps workbench">
    <section className="boot-panel">
      <div className="boot-panel__topline"><span>FABOPS / DECISION LAB</span><b>READ-ONLY PREVIEW</b></div>
      <div className="boot-panel__hero">
        <div className="boot-orb" aria-hidden="true"><span /><span /><span /></div>
        <div className="boot-lockup">
          <div className="boot-logo">FO</div>
          <div><span>INITIALIZING WORKSPACE</span><strong>Connecting operational evidence</strong><p>Synchronizing deterministic cases, source events, and projection freshness.</p></div>
        </div>
      </div>
      <div className="boot-progress" aria-hidden="true"><i /></div>
      <div className="boot-telemetry">
        <div><span>EVENT STREAM</span><strong>LINKING</strong><small>source ledger</small></div>
        <div><span>CASE PROJECTION</span><strong>SYNCING</strong><small>read model</small></div>
        <div><span>DECISION EVIDENCE</span><strong>VERIFYING</strong><small>human authority</small></div>
      </div>
      <footer><span className="console-live-dot" /> No equipment command path · synthetic portfolio evidence</footer>
    </section>
  </main>;
}

export default function App() {
  const [screen, setScreen] = useState<ScreenId>(() => screenFromPath(window.location.pathname));
  const [cockpit, setCockpit] = useState<DecisionCockpitResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetailResponse | null>(null);
  const [advisory, setAdvisory] = useState<AdvisoryResponse | null>(null);
  const [decisionBrief, setDecisionBrief] = useState<DecisionBriefResponse | null>(null);
  const [briefAudience, setBriefAudience] = useState<"manager" | "engineer">("manager");
  const [demoSessionToken, setDemoSessionToken] = useState<string | null>(null);
  const [narrationBusy, setNarrationBusy] = useState(false);
  const [narrationFeedback, setNarrationFeedback] = useState<string | null>(null);
  const [narrationStatus, setNarrationStatus] = useState<NarrationStatusResponse | null>(null);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{kind: "ok" | "error" | "unauthorized"; message: string} | null>(null);

  const loadRoot = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextCockpit, nextOverview, nextEvaluation, nextReplay] = await Promise.all([api.decisionCockpit(), api.overview(), api.evaluation(), api.replay()]);
      setCockpit(nextCockpit);
      setOverview(nextOverview);
      setEvaluation(nextEvaluation);
      setReplay(nextReplay);
      setSelectedCaseId((current) => current ?? nextCockpit.queue[0]?.case_id ?? nextOverview.cases[0]?.case_id ?? null);
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
  useEffect(() => {
    if (window.location.pathname === "/" || !Object.values(screenPaths).some((path) => path.toLowerCase() === window.location.pathname.replace(/\/+$/, "").toLowerCase())) {
      window.history.replaceState({screen}, "", screenPaths[screen]);
    }
    const handlePopState = () => setScreen(screenFromPath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);
  useEffect(() => { void api.narrationStatus().then(setNarrationStatus).catch(() => setNarrationStatus(null)); }, []);
  useEffect(() => { if (selectedCaseId) void loadCase(selectedCaseId); }, [loadCase, selectedCaseId]);
  useEffect(() => {
    if (!selectedCaseId || screen !== "decision") return;
    setDecisionBrief(null);
    void api.decisionBrief(selectedCaseId, briefAudience).then(setDecisionBrief).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Unable to load grounded decision brief");
    });
  }, [briefAudience, screen, selectedCaseId]);

  const selectedCase = useMemo(() => overview ? caseById(overview.cases, selectedCaseId) : null, [overview, selectedCaseId]);
  const selectedPacket = useMemo(() => cockpit?.queue.find((packet) => packet.case_id === selectedCaseId) ?? cockpit?.queue[0] ?? null, [cockpit, selectedCaseId]);

  function selectCase(caseId: string) {
    setSelectedCaseId(caseId);
    navigate("case");
    setFeedback(null);
  }

  function openDecision(caseId: string) {
    setSelectedCaseId(caseId);
    navigate("decision");
    setFeedback(null);
  }

  function navigate(next: ScreenId) {
    setScreen(next);
    if (window.location.pathname !== screenPaths[next]) window.history.pushState({screen: next}, "", screenPaths[next]);
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

  async function generateDemoBrief(intent: NarrationIntent) {
    if (!selectedCaseId) return;
    setNarrationBusy(true);
    setNarrationFeedback(null);
    try {
      let token = demoSessionToken;
      if (!token) {
        const session = await api.demoSession();
        token = session.token;
        setDemoSessionToken(token);
      }
      try {
        const generated = await api.demoNarration(token, selectedCaseId, briefAudience, intent);
        setDecisionBrief(generated);
        setNarrationFeedback(`Bounded AI demo · ${generated.brief.provider} · ${generated.brief.mode}`);
        void api.narrationStatus().then(setNarrationStatus).catch(() => undefined);
      } catch (reason) {
        const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
        if (status !== 401) throw reason;
        const session = await api.demoSession();
        setDemoSessionToken(session.token);
        const generated = await api.demoNarration(session.token, selectedCaseId, briefAudience, intent);
        setDecisionBrief(generated);
        setNarrationFeedback(`Bounded AI demo · ${generated.brief.provider} · ${generated.brief.mode}`);
        void api.narrationStatus().then(setNarrationStatus).catch(() => undefined);
      }
    } catch (reason) {
      const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
      setNarrationFeedback(status === 429 ? "AI demo limit reached. Cached/deterministic wording remains available." : "Live AI demo is unavailable; grounded deterministic wording remains available.");
    } finally {
      setNarrationBusy(false);
    }
  }

  if (loading && !overview) {
    return <InitialBoot />;
  }
  if (error && !overview) {
    return <main className="boot-state"><WorkbenchState kind="error" title="Workbench unavailable" detail={error} action={<button onClick={() => void loadRoot()}>Retry</button>} /></main>;
  }
  if (!cockpit || !overview || !evaluation || !replay) {
    return <main className="boot-state"><WorkbenchState kind="empty" title="No operational evidence" detail="The API returned no source state." /></main>;
  }

  let workSurface;
  if (screen === "cockpit") workSurface = <DecisionCockpit cockpit={cockpit} onOpenCase={selectCase} onOpenDecision={openDecision} />;
  else if (screen === "overview") workSurface = <OperationsOverview overview={overview} onSelectCase={selectCase} />;
  else if ((screen === "case" || screen === "graph" || screen === "decision") && !detail) workSurface = <WorkbenchState kind="loading" title="Loading selected case" detail="Fetching source-linked evidence and deterministic RCA." />;
  else if (screen === "case" && detail) workSurface = <ExcursionCase detail={detail} advisory={advisory} />;
  else if (screen === "graph" && detail) workSurface = <EvidenceGraph detail={detail} selectedStep={selectedStep} onSelectStep={setSelectedStep} />;
  else if (screen === "decision" && detail) workSurface = <DecisionApproval
    detail={detail}
    packet={selectedPacket}
    advisory={advisory}
    busy={busy}
    feedback={feedback}
    brief={decisionBrief}
    briefAudience={briefAudience}
    narrationBusy={narrationBusy}
    narrationFeedback={narrationFeedback}
    narrationStatus={narrationStatus}
    onBriefAudience={setBriefAudience}
    onGenerateBrief={generateDemoBrief}
    onRequestEvidence={(reason) => mutate(() => api.requestEvidence(detail.case.case_id, reason))}
    onPropose={(target, rationale) => mutate(() => api.propose(detail.case.case_id, target, rationale))}
    onApprove={(reason) => mutate(() => api.approve(detail.case.case_id, reason))}
    onReject={(reason) => mutate(() => api.reject(detail.case.case_id, reason))}
  />;
  else if (screen === "evaluation") workSurface = <EvaluationLab evaluation={evaluation} />;
  else workSurface = <ReplayOperations replay={replay} />;

  const navGroups = ["Decide", "Investigate", "Trust"] as const;

  return <div className="app-shell">
    <header className="global-header">
      <div className="brand-mark">FO</div>
      <div className="brand-copy"><strong>FabOps</strong><span>Decision intelligence for yield excursions</span></div>
      <div className="header-status">
        <span className="status-chip status-chip--candidate">0.7 CANDIDATE</span>
        <span className="status-chip">BASE {replay.release.release_version}</span>
        <span className="status-chip">SYNTHETIC</span>
        <span className="status-chip">READ-ONLY PREVIEW</span>
        <span className="status-chip status-chip--safe">NO TOOL CONTROL</span>
      </div>
    </header>
    <div className="mobile-status-ribbon" aria-label="Release and provenance status">
      <span>0.7 candidate</span><span>base {replay.release.release_version}</span><span>synthetic</span><span>read-only</span>
    </div>
    <aside className="left-rail" aria-label="Primary navigation">
      <div className="nav-heading"><span>Decision workspace</span><strong>From exception to governed action</strong></div>
      <nav>{navGroups.map((group) => <div className="nav-group" key={group}>
        <span className="nav-group__label">{group}</span>
        {navigation.filter((item) => item.group === group).map((item) => <button key={item.id} className={screen === item.id ? "nav-item is-active" : "nav-item"} aria-current={screen === item.id ? "page" : undefined} onClick={() => navigate(item.id)}>
          <span>{item.short}</span><strong>{item.label}</strong>
        </button>)}
      </div>)}</nav>
      <div className="case-object-list">
        <span className="section-label">Open decisions</span>
        {cockpit.queue.slice(0, 7).map((item) => <button key={item.case_id} className={item.case_id === selectedCaseId ? "case-object is-active" : "case-object"} onClick={() => openDecision(item.case_id)}>
          <span><b className={`case-priority-dot case-priority-dot--${item.priority_band.toLowerCase()}`} />{item.lot_id}</span>
          <small>{item.options.find((option) => option.option_id === item.recommended_option_id)?.label ?? item.classification.replaceAll("_", " ")}</small>
        </button>)}
      </div>
    </aside>
    <main id="work-surface" className="work-surface" tabIndex={-1}>{workSurface}</main>
    <EvidenceInspector selectedCase={detail?.case ?? selectedCase} selectedPacket={selectedPacket} projection={overview.projection} sourceTimestamp={overview.source_timestamp} selectedStep={selectedStep} />
  </div>;
}


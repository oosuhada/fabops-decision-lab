import {useCallback, useEffect, useMemo, useState} from "react";
import {api} from "./api";
import {EvidenceInspector, WorkbenchState} from "./components";
import {AnalysisWorkbench} from "./features/analysis/AnalysisWorkbench";
import {CaseComparisonWorkbench} from "./features/comparison/CaseComparisonWorkbench";
import type {EvidenceGraphNode} from "./features/evidence/evidenceGraphModel";
import {ShiftHandoffBrief} from "./features/handoff/ShiftHandoffBrief";
import {WorkbenchResizeHandle} from "./platform/workbench/WorkbenchResizeHandle";
import {useWorkbenchLayout} from "./platform/workbench/useWorkbenchLayout";
import {useLocale} from "./locale";
import {DecisionApproval, DecisionCockpit, EvaluationLab, EvidenceGraph, ExcursionCase, OperationsOverview, ReplayOperations, caseById} from "./screens";
import type {AdvisoryResponse, CaseDetailResponse, CaseReplayTraceResponse, ContinuousIntelligenceStatus, DecisionBriefResponse, DecisionCockpitResponse, DeploymentIdentityResponse, EvaluationResponse, LiveStatusResponse, NarrationIntent, NarrationStatusResponse, OverviewResponse, ReplayResponse, ScreenId} from "./types";

const navigation: Array<{id: ScreenId; label: string; short: string; group: "Decide" | "Investigate" | "Trust"}> = [
  {id: "cockpit", label: "Decision Cockpit", short: "01", group: "Decide"},
  {id: "decision", label: "Decision & Approval", short: "02", group: "Decide"},
  {id: "handoff", label: "Shift Handoff", short: "03", group: "Decide"},
  {id: "case", label: "Case Investigation", short: "04", group: "Investigate"},
  {id: "graph", label: "Evidence Graph", short: "05", group: "Investigate"},
  {id: "analysis", label: "Analysis Workbench", short: "06", group: "Investigate"},
  {id: "compare", label: "Case Comparison", short: "07", group: "Investigate"},
  {id: "overview", label: "Operations Queue", short: "08", group: "Investigate"},
  {id: "evaluation", label: "Model & Evidence", short: "09", group: "Trust"},
  {id: "replay", label: "System Health", short: "10", group: "Trust"},
];

const navigationGroups = [
  {name: "Decide", numeral: "Ⅰ", section: 1},
  {name: "Investigate", numeral: "Ⅱ", section: 2},
  {name: "Trust", numeral: "Ⅲ", section: 3},
] as const;

type NavigationGroupName = typeof navigationGroups[number]["name"];
const NAV_GROUP_STORAGE_KEY = "fabops:nav-groups";

function readNavigationGroups(): Record<NavigationGroupName, boolean> {
  const fallback: Record<NavigationGroupName, boolean> = {Decide: true, Investigate: true, Trust: true};
  try {
    const raw = window.localStorage.getItem(NAV_GROUP_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Record<NavigationGroupName, unknown>>;
    return {
      Decide: typeof parsed.Decide === "boolean" ? parsed.Decide : true,
      Investigate: typeof parsed.Investigate === "boolean" ? parsed.Investigate : true,
      Trust: typeof parsed.Trust === "boolean" ? parsed.Trust : true,
    };
  } catch {
    return fallback;
  }
}

const screenPaths: Record<ScreenId, string> = {
  cockpit: "/DecisionCockpit",
  decision: "/DecisionApproval",
  handoff: "/ShiftHandoff",
  case: "/CaseInvestigation",
  graph: "/EvidenceGraph",
  analysis: "/AnalysisWorkbench",
  compare: "/CaseComparison",
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
  const {locale, setLocale} = useLocale();
  const workbench = useWorkbenchLayout();
  const [openGroups, setOpenGroups] = useState<Record<NavigationGroupName, boolean>>(readNavigationGroups);
  const [screen, setScreen] = useState<ScreenId>(() => screenFromPath(window.location.pathname));
  const [cockpit, setCockpit] = useState<DecisionCockpitResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [deploymentIdentity, setDeploymentIdentity] = useState<DeploymentIdentityResponse | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveStatusResponse | null>(null);
  const [intelligenceStatus, setIntelligenceStatus] = useState<ContinuousIntelligenceStatus | null>(null);
  const [caseReplayTrace, setCaseReplayTrace] = useState<CaseReplayTraceResponse | null>(null);
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
  const [selectedEvidenceNode, setSelectedEvidenceNode] = useState<EvidenceGraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{kind: "ok" | "error" | "unauthorized"; message: string} | null>(null);

  const loadRoot = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextCockpit, nextOverview, nextEvaluation, nextReplay, nextDeploymentIdentity] = await Promise.all([api.decisionCockpit(), api.overview(), api.evaluation(), api.replay(), api.deploymentIdentity()]);
      setCockpit(nextCockpit);
      setOverview(nextOverview);
      setEvaluation(nextEvaluation);
      setReplay(nextReplay);
      setDeploymentIdentity(nextDeploymentIdentity);
      setSelectedCaseId((current) => current ?? nextCockpit.queue[0]?.case_id ?? nextOverview.cases[0]?.case_id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load workbench data");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCase = useCallback(async (caseId: string) => {
    try {
      const [nextDetail, nextAdvisory, nextReplayTrace] = await Promise.all([api.caseDetail(caseId), api.advisory(caseId), api.caseReplayTrace(caseId)]);
      setDetail(nextDetail);
      setAdvisory(nextAdvisory);
      setCaseReplayTrace(nextReplayTrace);
      setSelectedStep((current) => current && nextDetail.trace.process_path.some((item) => item.step_id === current) ? current : nextDetail.trace.process_path[0]?.step_id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load selected case");
    }
  }, []);

  const loadLiveStatus = useCallback(async () => {
    try {
      setLiveStatus(await api.liveStatus());
    } catch {
      setLiveStatus(null);
    }
  }, []);

  const loadIntelligenceStatus = useCallback(async () => {
    try {
      setIntelligenceStatus(await api.intelligenceStatus());
    } catch {
      setIntelligenceStatus(null);
    }
  }, []);

  useEffect(() => { void loadRoot(); }, [loadRoot]);
  useEffect(() => { void loadLiveStatus(); }, [loadLiveStatus]);
  useEffect(() => { void loadIntelligenceStatus(); }, [loadIntelligenceStatus]);
  useEffect(() => {
    try { window.localStorage.setItem(NAV_GROUP_STORAGE_KEY, JSON.stringify(openGroups)); } catch { /* Storage is optional for the preview. */ }
  }, [openGroups]);
  useEffect(() => {
    if (window.location.pathname === "/" || !Object.values(screenPaths).some((path) => path.toLowerCase() === window.location.pathname.replace(/\/+$/, "").toLowerCase())) {
      window.history.replaceState({screen}, "", screenPaths[screen]);
    }
    const handlePopState = () => setScreen(screenFromPath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);
  useEffect(() => { void api.narrationStatus().then(setNarrationStatus).catch(() => setNarrationStatus(null)); }, []);
  useEffect(() => {
    setSelectedEvidenceNode(null);
    if (selectedCaseId) void loadCase(selectedCaseId);
  }, [loadCase, selectedCaseId]);
  useEffect(() => {
    if (!selectedCaseId || screen !== "decision") return;
    setDecisionBrief(null);
    void api.decisionBrief(selectedCaseId, briefAudience).then(setDecisionBrief).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Unable to load grounded decision brief");
    });
  }, [briefAudience, screen, selectedCaseId]);
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(api.liveStreamUrl());
    const refresh = (event: Event) => {
      const message = event as MessageEvent<string>;
      try {
        setLiveStatus(JSON.parse(message.data) as LiveStatusResponse);
      } catch {
        void loadLiveStatus();
      }
    };
    source.addEventListener("fabops-update", refresh);
    return () => {
      source.removeEventListener("fabops-update", refresh);
      source.close();
    };
  }, [loadLiveStatus]);
  useEffect(() => {
    if (!liveStatus?.live_enabled) return;
    const timer = window.setInterval(() => {
      void loadRoot();
      void loadLiveStatus();
      void loadIntelligenceStatus();
      if (selectedCaseId) void loadCase(selectedCaseId);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [liveStatus?.live_enabled, loadCase, loadIntelligenceStatus, loadLiveStatus, loadRoot, selectedCaseId]);

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

  function toggleNavigationGroup(group: NavigationGroupName) {
    setOpenGroups((current) => ({...current, [group]: !current[group]}));
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
  if (!cockpit || !overview || !evaluation || !replay || !deploymentIdentity) {
    return <main className="boot-state"><WorkbenchState kind="empty" title="No operational evidence" detail="The API returned no source state." /></main>;
  }

  let workSurface;
  if (screen === "cockpit") workSurface = <DecisionCockpit cockpit={cockpit} detail={detail} projection={overview.projection} sourceTimestamp={overview.source_timestamp} liveStatus={liveStatus} intelligence={intelligenceStatus} selectedCaseId={selectedCaseId} onOpenCase={selectCase} onOpenDecision={openDecision} />;
  else if (screen === "overview") workSurface = <OperationsOverview overview={overview} liveStatus={liveStatus} intelligence={intelligenceStatus} onSelectCase={selectCase} />;
  else if ((screen === "case" || screen === "graph" || screen === "analysis" || screen === "decision") && !detail) workSurface = <WorkbenchState kind="loading" title="Loading selected case" detail="Fetching source-linked evidence and deterministic RCA." />;
  else if (screen === "case" && detail) workSurface = <ExcursionCase detail={detail} advisory={advisory} />;
  else if (screen === "graph" && detail) workSurface = <EvidenceGraph detail={detail} selectedStep={selectedStep} onSelectStep={setSelectedStep} onSelectEvidenceNode={setSelectedEvidenceNode} />;
  else if (screen === "analysis" && detail) workSurface = <AnalysisWorkbench detail={detail} />;
  else if (screen === "compare") workSurface = <CaseComparisonWorkbench packets={cockpit.queue} />;
  else if (screen === "handoff") workSurface = <ShiftHandoffBrief cockpit={cockpit} overview={overview} replay={replay} />;
  else if (screen === "decision" && detail) workSurface = <DecisionApproval
    detail={detail}
    packet={selectedPacket}
    replayTrace={caseReplayTrace}
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
  else workSurface = <ReplayOperations replay={replay} trace={caseReplayTrace} />;

  const activeNavigation = navigation.find((item) => item.id === screen) ?? navigation[0];
  const candidateSha = deploymentIdentity.candidate?.git_sha ?? null;
  const candidateShortSha = candidateSha?.slice(0, 10) ?? "metadata unavailable";
  const candidateLabel = deploymentIdentity.candidate?.label ?? "candidate metadata unavailable";
  const primaryDeploymentLabel = deploymentIdentity.deployment_kind === "candidate" ? "CANDIDATE BUILD" : "OFFICIAL RELEASE";

  return <div className="app-shell" style={workbench.shellStyle}>
    <header className="global-header">
      <div className="brand-copy"><strong>FabOps</strong><span>Decision intelligence for yield excursions</span></div>
      <div className="deployment-identity-strip" aria-label="Deployment identity">
        <div className="deployment-identity-strip__primary">
          <span>{primaryDeploymentLabel}</span>
          <strong>{deploymentIdentity.deployment_kind === "candidate" ? candidateLabel : deploymentIdentity.base_release.version}</strong>
          <code title={candidateSha ?? undefined}>{deploymentIdentity.deployment_kind === "candidate" ? candidateShortSha : deploymentIdentity.base_release.source_git_commit?.slice(0, 10) ?? "manifest"}</code>
        </div>
        <div>
          <span>BASE RELEASE</span>
          <strong>{deploymentIdentity.base_release.version}</strong>
          <small>authoritative release identity</small>
        </div>
        <div>
          <span>{deploymentIdentity.channel.replaceAll("-", " ").toUpperCase()}</span>
          <strong>READ-ONLY</strong>
          <small>bounded AI · no equipment control</small>
        </div>
      </div>
      <div className="locale-switch" role="group" aria-label="Language">
        <button type="button" aria-pressed={locale === "en"} onClick={() => setLocale("en")}>EN</button>
        <button type="button" aria-pressed={locale === "ko"} onClick={() => setLocale("ko")}>한국어</button>
      </div>
    </header>
    <div className="workspace-context" aria-label="Current workspace context">
      <div className="workspace-context__route">
        <span>Decision Lab</span>
        <i aria-hidden="true">/</i>
        <span>{activeNavigation.group}</span>
        <i aria-hidden="true">/</i>
        <strong>{activeNavigation.label}</strong>
      </div>
      <div className="workspace-context__object">
        <span>Current object</span>
        <strong>{selectedPacket?.lot_id ?? selectedCase?.lot_id ?? "No case selected"}</strong>
        {selectedPacket ? <span className={`workspace-context__priority workspace-context__priority--${selectedPacket.priority_band.toLowerCase()}`}>{selectedPacket.priority_band}</span> : null}
        <span className="workspace-context__layout-controls" aria-label="Workbench pane controls">
          <button type="button" aria-label={workbench.layout.leftOpen ? "Unpin navigation pane" : "Pin navigation pane"} aria-pressed={workbench.layout.leftOpen} onClick={() => workbench.togglePin("left")}>{workbench.layout.leftOpen ? "Unpin navigation" : "Pin navigation"}</button>
          <button type="button" aria-label={workbench.layout.rightOpen ? "Unpin inspector pane" : "Pin inspector pane"} aria-pressed={workbench.layout.rightOpen} onClick={() => workbench.togglePin("right")}>{workbench.layout.rightOpen ? "Unpin inspector" : "Pin inspector"}</button>
        </span>
      </div>
    </div>
    <div className="mobile-status-ribbon" aria-label="Release and provenance status">
      <span>{deploymentIdentity.deployment_kind === "candidate" ? `candidate ${candidateShortSha}` : `official ${deploymentIdentity.base_release.version}`}</span><span>base {deploymentIdentity.base_release.version}</span><span>human authority</span><span>no equipment control</span>
    </div>
    {workbench.isDesktop ? <button type="button" className="pane-edge-trigger pane-edge-trigger--left" aria-label="Open navigation pane" aria-expanded={workbench.leftVisible} onMouseEnter={() => workbench.previewPane("left")} onFocus={() => workbench.previewPane("left")} onClick={() => workbench.previewPane("left")}><span>Navigation</span></button> : null}
    <aside className={`${workbench.leftVisible ? "left-rail" : "left-rail is-collapsed"}${workbench.isDesktop && !workbench.layout.leftOpen ? " is-overlay" : ""}`} aria-label="Primary navigation" aria-hidden={!workbench.leftVisible} onMouseEnter={() => workbench.previewPane("left")} onMouseLeave={() => workbench.dismissPane("left")}>
      {workbench.leftVisible ? <>
      <div className="pane-pin-toolbar pane-pin-toolbar--dark"><button type="button" aria-label={workbench.layout.leftOpen ? "Unpin navigation pane" : "Pin navigation pane"} aria-pressed={workbench.layout.leftOpen} onClick={() => workbench.togglePin("left")}><span aria-hidden="true">{workbench.layout.leftOpen ? "↤" : "⌖"}</span>{workbench.layout.leftOpen ? "Unpin navigation" : "Pin navigation"}</button></div>
      <div className="nav-heading"><span>Decision workspace</span><strong>From exception to governed action</strong></div>
      <nav>{navigationGroups.map((group) => <div className="nav-group" key={group.name}>
        <button type="button" className="nav-group__label" aria-label={`Section ${group.section}, ${group.name}`} aria-expanded={openGroups[group.name]} aria-controls={`nav-group-panel-${group.section}`} onClick={() => toggleNavigationGroup(group.name)}>
          <span><b aria-hidden="true">{group.numeral}.</b>{" "}<strong>{group.name}</strong></span><i aria-hidden="true">{openGroups[group.name] ? "⌄" : "›"}</i>
        </button>
        <div id={`nav-group-panel-${group.section}`} className="nav-group__panel" hidden={workbench.isDesktop && !openGroups[group.name]}>
          {navigation.filter((item) => item.group === group.name).map((item) => <button key={item.id} className={screen === item.id ? "nav-item is-active" : "nav-item"} aria-current={screen === item.id ? "page" : undefined} onClick={() => navigate(item.id)}>
            <span>{item.short}</span><strong>{item.label}</strong>
          </button>)}
        </div>
      </div>)}</nav>
      <div className="case-object-list">
        <span className="section-label">Open decisions</span>
        {cockpit.queue.slice(0, 7).map((item) => <button key={item.case_id} className={item.case_id === selectedCaseId ? "case-object is-active" : "case-object"} onClick={() => openDecision(item.case_id)}>
          <span><b className={`case-priority-dot case-priority-dot--${item.priority_band.toLowerCase()}`} />{item.lot_id}</span>
          <small>{item.options.find((option) => option.option_id === item.recommended_option_id)?.label ?? item.classification.replaceAll("_", " ")}</small>
        </button>)}
      </div>
      </> : null}
    </aside>
    {workbench.layout.leftOpen ? <WorkbenchResizeHandle side="left" width={workbench.layout.leftWidth} onBegin={workbench.beginResize} onMove={workbench.moveResize} onEnd={workbench.endResize} onKeyboardResize={workbench.keyboardResize} onReset={workbench.resetWidth} /> : null}
    <main id="work-surface" className="work-surface" tabIndex={-1} onMouseEnter={() => { workbench.dismissPane("left"); workbench.dismissPane("right"); }} onClick={() => { workbench.dismissPane("left"); workbench.dismissPane("right"); }}>{workSurface}</main>
    {workbench.layout.rightOpen ? <WorkbenchResizeHandle side="right" width={workbench.layout.rightWidth} onBegin={workbench.beginResize} onMove={workbench.moveResize} onEnd={workbench.endResize} onKeyboardResize={workbench.keyboardResize} onReset={workbench.resetWidth} /> : null}
    {workbench.isDesktop ? <button type="button" className="pane-edge-trigger pane-edge-trigger--right" aria-label="Open inspector pane" aria-expanded={workbench.rightVisible} onMouseEnter={() => workbench.previewPane("right")} onFocus={() => workbench.previewPane("right")} onClick={() => workbench.previewPane("right")}><span>Inspector</span></button> : null}
    <div className={`${workbench.rightVisible ? "evidence-inspector-slot" : "evidence-inspector-slot is-collapsed"}${workbench.isDesktop && !workbench.layout.rightOpen ? " is-overlay" : ""}`} aria-hidden={!workbench.rightVisible} onMouseEnter={() => workbench.previewPane("right")} onMouseLeave={() => workbench.dismissPane("right")}>
      {workbench.rightVisible ? <><div className="pane-pin-toolbar"><button type="button" aria-label={workbench.layout.rightOpen ? "Unpin inspector pane" : "Pin inspector pane"} aria-pressed={workbench.layout.rightOpen} onClick={() => workbench.togglePin("right")}><span aria-hidden="true">{workbench.layout.rightOpen ? "↦" : "⌖"}</span>{workbench.layout.rightOpen ? "Unpin inspector" : "Pin inspector"}</button></div><EvidenceInspector selectedCase={detail?.case ?? selectedCase} selectedPacket={selectedPacket} projection={overview.projection} sourceTimestamp={overview.source_timestamp} selectedStep={selectedStep} selectedEvidenceNode={selectedEvidenceNode} /></> : null}
    </div>
  </div>;
}

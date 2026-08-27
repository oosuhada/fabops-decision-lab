import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {api} from "./api";
import {EvidenceInspector, WorkbenchState} from "./components";
import {AnalysisWorkbench} from "./features/analysis/AnalysisWorkbench";
import {CaseComparisonWorkbench} from "./features/comparison/CaseComparisonWorkbench";
import type {EvidenceGraphNode} from "./features/evidence/evidenceGraphModel";
import {ShiftHandoffBrief} from "./features/handoff/ShiftHandoffBrief";
import {CaseContextHydration, CaseHydrationExperience} from "./features/loading/CaseHydrationExperience";
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

type BootStage = "ledger" | "cases" | "intelligence" | "workspace";
const BOOT_STAGE_ORDER: Record<BootStage, number> = {ledger: 0, cases: 1, intelligence: 2, workspace: 3};

interface CaseHydrationState {
  caseId: string | null;
  startedAt: number;
  advisoryPending: boolean;
  replayPending: boolean;
}

function InitialBoot({stage}: {stage: BootStage}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((current) => current + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const stageIndex = BOOT_STAGE_ORDER[stage];
  const stages = [
    ["LIVE EVENT LEDGER", "CONNECTING", "streaming source-of-truth"],
    ["ONLINE DETECTION", "HYDRATING", "case + RCA projection"],
    ["LEARNED INTELLIGENCE", "WARMING", "champion models + feedback"],
    ["ADAPTIVE WORKBENCH", "ASSEMBLING", "live views + decision context"],
  ] as const;
  return <main className="boot-experience" aria-label="Loading FabOps workbench">
    <section className="boot-panel">
      <div className="boot-panel__topline"><span>FABOPS / CONTINUOUS DECISION INTELLIGENCE</span><b>READ-ONLY LIVE PREVIEW</b></div>
      <div className="boot-panel__hero">
        <div className="boot-orb" aria-hidden="true"><span /><span /><span /></div>
        <div className="boot-lockup">
          <div className="boot-logo">FO</div>
          <div><span>INITIALIZING LIVE INTELLIGENCE</span><strong>Connecting the evidence-to-prediction loop</strong><p>Restoring the live ledger, online cases, champion models, prediction feedback, and adaptive decision views.</p></div>
        </div>
      </div>
      <div className="boot-progress boot-progress--staged" aria-hidden="true"><i style={{width: `${24 + stageIndex * 24}%`}} /></div>
      <div className="boot-telemetry">
        {stages.map(([label, active, detail], index) => <div key={label} className={index < stageIndex ? "is-complete" : index === stageIndex ? "is-active" : "is-pending"}>
          <span>{label}</span><strong>{index < stageIndex ? "READY" : index === stageIndex ? active : "QUEUED"}</strong><small>{detail}</small>
        </div>)}
      </div>
      <div className="boot-heartbeat"><span><i /> runtime heartbeat</span><b>{elapsed}s</b><small>Data services continue running while the UI hydrates.</small></div>
      <footer><span className="console-live-dot" /> Continuous learning preview · no equipment command path · synthetic portfolio evidence</footer>
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
  const [cockpitBrief, setCockpitBrief] = useState<DecisionBriefResponse | null>(null);
  const [cockpitAnalyzing, setCockpitAnalyzing] = useState(false);
  const [cockpitAnalysisFeedback, setCockpitAnalysisFeedback] = useState<string | null>(null);
  const [briefAudience, setBriefAudience] = useState<"manager" | "engineer">("manager");
  const [demoSessionToken, setDemoSessionToken] = useState<string | null>(null);
  const [narrationBusy, setNarrationBusy] = useState(false);
  const [narrationFeedback, setNarrationFeedback] = useState<string | null>(null);
  const [narrationStatus, setNarrationStatus] = useState<NarrationStatusResponse | null>(null);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [selectedEvidenceNode, setSelectedEvidenceNode] = useState<EvidenceGraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootStage, setBootStage] = useState<BootStage>("ledger");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{kind: "ok" | "error" | "unauthorized"; message: string} | null>(null);
  const initialRootLoaded = useRef(false);
  const caseDetailCache = useRef(new Map<string, CaseDetailResponse>());
  const caseDetailInflight = useRef(new Map<string, Promise<CaseDetailResponse>>());
  const caseLoadSerial = useRef(0);
  const [caseHydration, setCaseHydration] = useState<CaseHydrationState>({
    caseId: null,
    startedAt: Date.now(),
    advisoryPending: false,
    replayPending: false,
  });

  const loadRoot = useCallback(async () => {
    const isInitialLoad = !initialRootLoaded.current;
    if (isInitialLoad) setLoading(true);
    setError("");
    try {
      if (isInitialLoad) setBootStage("ledger");
      const advanceBootStage = (next: BootStage) => setBootStage((current) => BOOT_STAGE_ORDER[next] > BOOT_STAGE_ORDER[current] ? next : current);
      const overviewPromise = api.overview().then((value) => { if (isInitialLoad) advanceBootStage("cases"); return value; });
      const cockpitPromise = api.decisionCockpit().then((value) => { if (isInitialLoad) advanceBootStage("intelligence"); return value; });
      const identityPromise = isInitialLoad ? api.deploymentIdentity() : Promise.resolve<DeploymentIdentityResponse | null>(null);
      const [nextCockpit, nextOverview, nextDeploymentIdentity] = await Promise.all([cockpitPromise, overviewPromise, identityPromise]);
      setCockpit(nextCockpit);
      setOverview(nextOverview);
      if (nextDeploymentIdentity) setDeploymentIdentity(nextDeploymentIdentity);
      setSelectedCaseId((current) => current ?? nextCockpit.queue[0]?.case_id ?? nextOverview.cases[0]?.case_id ?? null);
      if (isInitialLoad) {
        advanceBootStage("workspace");
        initialRootLoaded.current = true;
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load workbench data");
    } finally {
      if (isInitialLoad) setLoading(false);
    }
  }, []);

  const loadCase = useCallback(async (caseId: string, options: {hydrateContext?: boolean; refresh?: boolean} = {}) => {
    const hydrateContext = options.hydrateContext !== false;
    const refresh = options.refresh === true;
    const requestId = ++caseLoadSerial.current;
    const startedAt = Date.now();
    const cached = caseDetailCache.current.get(caseId) ?? null;
    if (cached) {
      setDetail(cached);
    } else {
      setDetail((current) => current?.case.case_id === caseId ? current : null);
      setCaseHydration({caseId, startedAt, advisoryPending: false, replayPending: false});
    }
    if (hydrateContext) {
      setAdvisory(null);
      setCaseReplayTrace(null);
    }

    const hydrateSecondaryContext = () => {
      if (!hydrateContext) return;
      setCaseHydration({caseId, startedAt, advisoryPending: true, replayPending: true});
      void api.advisory(caseId).then((nextAdvisory) => {
        if (caseLoadSerial.current !== requestId) return;
        setAdvisory(nextAdvisory);
        setCaseHydration((current) => current.caseId === caseId ? {...current, advisoryPending: false} : current);
      }).catch(() => {
        if (caseLoadSerial.current !== requestId) return;
        setCaseHydration((current) => current.caseId === caseId ? {...current, advisoryPending: false} : current);
      });
      void api.caseReplayTrace(caseId).then((nextTrace) => {
        if (caseLoadSerial.current !== requestId) return;
        setCaseReplayTrace(nextTrace);
        setCaseHydration((current) => current.caseId === caseId ? {...current, replayPending: false} : current);
      }).catch(() => {
        if (caseLoadSerial.current !== requestId) return;
        setCaseHydration((current) => current.caseId === caseId ? {...current, replayPending: false} : current);
      });
    };

    if (cached && !refresh) {
      hydrateSecondaryContext();
      return;
    }
    try {
      let detailRequest = caseDetailInflight.current.get(caseId);
      if (!detailRequest) {
        detailRequest = api.caseDetail(caseId);
        caseDetailInflight.current.set(caseId, detailRequest);
        void detailRequest.finally(() => {
          if (caseDetailInflight.current.get(caseId) === detailRequest) caseDetailInflight.current.delete(caseId);
        }).catch(() => undefined);
      }
      const nextDetail = await detailRequest;
      if (caseLoadSerial.current !== requestId) return;
      caseDetailCache.current.set(caseId, nextDetail);
      setDetail(nextDetail);
      setSelectedStep((current) => current && nextDetail.trace.process_path.some((item) => item.step_id === current) ? current : nextDetail.trace.process_path[0]?.step_id ?? null);
      hydrateSecondaryContext();
    } catch (reason) {
      if (caseLoadSerial.current !== requestId) return;
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
    if (loading || !overview) return;
    if (!evaluation) void api.evaluation().then(setEvaluation).catch(() => undefined);
    if (!replay) void api.replay().then(setReplay).catch(() => undefined);
  }, [evaluation, loading, overview, replay]);
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
    setCockpitBrief(null);
    setCockpitAnalysisFeedback(null);
    if (selectedCaseId) void loadCase(selectedCaseId, {hydrateContext: screen === "case" || screen === "decision"});
  }, [loadCase, screen, selectedCaseId]);
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
      if (selectedCaseId && detail?.case.case_id === selectedCaseId) void loadCase(selectedCaseId, {hydrateContext: false, refresh: true});
    }, 15000);
    return () => window.clearInterval(timer);
  }, [detail?.case.case_id, liveStatus?.live_enabled, loadCase, loadIntelligenceStatus, loadLiveStatus, loadRoot, selectedCaseId]);
  useEffect(() => {
    if (!liveStatus?.live_enabled || screen !== "replay") return;
    const timer = window.setInterval(() => void api.replay().then(setReplay).catch(() => undefined), 60000);
    return () => window.clearInterval(timer);
  }, [liveStatus?.live_enabled, screen]);

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
      await Promise.all([loadRoot(), loadCase(selectedCaseId, {hydrateContext: true, refresh: true})]);
      setFeedback({kind: "ok", message: "The append-only workflow ledger and current case state were updated."});
    } catch (reason) {
      const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
      setFeedback({kind: status === 403 ? "unauthorized" : "error", message: reason instanceof Error ? reason.message : "Workflow action failed"});
    } finally {
      setBusy(false);
    }
  }

  async function requestDemoNarration(caseId: string, audience: "manager" | "engineer", intent: NarrationIntent) {
    let token = demoSessionToken;
    if (!token) {
      const session = await api.demoSession();
      token = session.token;
      setDemoSessionToken(token);
    }
    try {
      return await api.demoNarration(token, caseId, audience, intent);
    } catch (reason) {
      const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
      if (status !== 401) throw reason;
      const session = await api.demoSession();
      setDemoSessionToken(session.token);
      return api.demoNarration(session.token, caseId, audience, intent);
    }
  }

  async function generateDemoBrief(intent: NarrationIntent) {
    if (!selectedCaseId) return;
    setNarrationBusy(true);
    setNarrationFeedback(null);
    try {
      const generated = await requestDemoNarration(selectedCaseId, briefAudience, intent);
      setDecisionBrief(generated);
      setNarrationFeedback(`Bounded AI demo · ${generated.brief.provider} · ${generated.brief.mode}`);
      void api.narrationStatus().then(setNarrationStatus).catch(() => undefined);
    } catch (reason) {
      const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
      setNarrationFeedback(status === 429 ? "AI demo limit reached. Cached/deterministic wording remains available." : "Live AI demo is unavailable; grounded deterministic wording remains available.");
    } finally {
      setNarrationBusy(false);
    }
  }

  async function analyzeCockpitNow() {
    const caseId = selectedPacket?.case_id ?? selectedCaseId;
    if (!caseId) return;
    setCockpitAnalyzing(true);
    setCockpitAnalysisFeedback("LOCAL QWEN QUEUE · 요청을 등록하고 있습니다.");
    try {
      const generated = await requestDemoNarration(caseId, "engineer", "situation_update");
      setCockpitBrief(generated);
      const queued = generated.inference_job;
      if (!queued) {
        setCockpitAnalysisFeedback(`${generated.brief.cache_hit ? "CACHED" : generated.brief.provider.toUpperCase()} · ${generated.brief.mode}`);
        void loadRoot();
        void loadIntelligenceStatus();
        return;
      }
      let currentJob = queued;
      const terminal = new Set(["COMPLETED", "FALLBACK", "FAILED", "EXPIRED", "CANCELLED"]);
      for (let attempt = 0; attempt < 100 && !terminal.has(currentJob.status); attempt += 1) {
        const position = currentJob.queue_position ? ` · QUEUED #${currentJob.queue_position}` : "";
        const label = currentJob.status === "WAITING_FOR_LOCAL"
          ? "LOCAL QWEN BUSY · WAITING FOR LOCAL MODEL"
          : currentJob.status === "RUNNING"
            ? "LOCAL QWEN RUNNING"
            : currentJob.status === "RETRY"
              ? "LOCAL QWEN RETRY"
              : "LOCAL QWEN QUEUED";
        setCockpitAnalysisFeedback(`${label}${position}`);
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        currentJob = (await api.inferenceJob(currentJob.job_id)).job;
      }
      const resultBrief = currentJob.result?.brief;
      if (resultBrief) {
        setCockpitBrief({
          ...generated,
          source: "durable-inference-queue",
          brief: resultBrief,
          assessment_persisted: Boolean(currentJob.result?.assessment_persisted),
          inference_job: currentJob,
        });
      }
      if (currentJob.status === "COMPLETED") {
        setCockpitAnalysisFeedback(`LOCAL QWEN · COMPLETE · ${currentJob.result?.assessment_persisted ? "assessment history 저장 완료" : "result ready"}`);
      } else if (currentJob.status === "FALLBACK") {
        const provider = resultBrief?.provider === "vertex-ai-gemini" ? "VERTEX FALLBACK" : resultBrief?.provider === "deterministic" ? "DETERMINISTIC" : "FALLBACK";
        setCockpitAnalysisFeedback(`${provider} · local wait budget 이후 완료`);
      } else if (currentJob.status === "EXPIRED") {
        setCockpitAnalysisFeedback("LOCAL QWEN QUEUE EXPIRED · 기존 assessment를 유지합니다.");
      } else if (currentJob.status === "FAILED" || currentJob.status === "CANCELLED") {
        setCockpitAnalysisFeedback(`${currentJob.status} · 기존 assessment를 유지합니다.`);
      } else {
        setCockpitAnalysisFeedback(`${currentJob.status} · background queue에서 계속 처리됩니다.`);
      }
      void loadRoot();
      void loadIntelligenceStatus();
    } catch (reason) {
      const status = typeof reason === "object" && reason !== null && "status" in reason ? Number((reason as {status: number}).status) : 0;
      setCockpitAnalysisFeedback(status === 429 ? "AI 분석 호출 한도에 도달했습니다. 자동 분석 결과는 계속 갱신됩니다." : "즉시 AI 분석에 실패했습니다. 자동 분석과 학습 모델 결과는 계속 유지됩니다.");
    } finally {
      setCockpitAnalyzing(false);
    }
  }

  if (loading && !overview) {
    return <InitialBoot stage={bootStage} />;
  }
  if (error && !overview) {
    return <main className="boot-state"><WorkbenchState kind="error" title="Workbench unavailable" detail={error} action={<button onClick={() => void loadRoot()}>Retry</button>} /></main>;
  }
  if (!cockpit || !overview || !deploymentIdentity) {
    return <main className="boot-state"><WorkbenchState kind="empty" title="No operational evidence" detail="The API returned no source state." /></main>;
  }

  let workSurface;
  if (screen === "cockpit") workSurface = <DecisionCockpit cockpit={cockpit} detail={detail} projection={overview.projection} sourceTimestamp={overview.source_timestamp} liveStatus={liveStatus} intelligence={intelligenceStatus} manualBrief={cockpitBrief} analyzing={cockpitAnalyzing} analysisFeedback={cockpitAnalysisFeedback} selectedCaseId={selectedCaseId} onAnalyzeNow={analyzeCockpitNow} onOpenCase={selectCase} onOpenDecision={openDecision} />;
  else if (screen === "overview") workSurface = <OperationsOverview overview={overview} liveStatus={liveStatus} intelligence={intelligenceStatus} onSelectCase={selectCase} />;
  else if ((screen === "case" || screen === "graph" || screen === "analysis" || screen === "decision") && !detail) workSurface = <CaseHydrationExperience
    screen={screen}
    caseId={selectedCaseId}
    lotId={selectedPacket?.lot_id ?? selectedCase?.lot_id ?? null}
    startedAt={caseHydration.caseId === selectedCaseId ? caseHydration.startedAt : Date.now()}
  />;
  else if (screen === "case" && detail) workSurface = <ExcursionCase detail={detail} advisory={advisory} />;
  else if (screen === "graph" && detail) workSurface = <EvidenceGraph detail={detail} selectedStep={selectedStep} onSelectStep={setSelectedStep} onSelectEvidenceNode={setSelectedEvidenceNode} />;
  else if (screen === "analysis" && detail) workSurface = <AnalysisWorkbench detail={detail} />;
  else if (screen === "compare") workSurface = <CaseComparisonWorkbench packets={cockpit.queue} />;
  else if (screen === "handoff" && replay) workSurface = <ShiftHandoffBrief cockpit={cockpit} overview={overview} replay={replay} />;
  else if (screen === "handoff") workSurface = <WorkbenchState kind="loading" title="Building shift handoff" detail="The decision queue is already available. Replay context is hydrating separately." />;
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
  else if (screen === "evaluation" && evaluation) workSurface = <EvaluationLab evaluation={evaluation} />;
  else if (screen === "evaluation") workSurface = <WorkbenchState kind="loading" title="Loading model evidence" detail="The operational workspace is already usable. Historical evaluation evidence is loading independently." />;
  else if (replay) workSurface = <ReplayOperations replay={replay} trace={caseReplayTrace} />;
  else workSurface = <WorkbenchState kind="loading" title="Loading system health" detail="The live runtime is available. Replay and integration diagnostics are hydrating independently." />;

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
    <main id="work-surface" className="work-surface" tabIndex={-1} onMouseEnter={() => { workbench.dismissPane("left"); workbench.dismissPane("right"); }} onClick={() => { workbench.dismissPane("left"); workbench.dismissPane("right"); }}>
      {(screen === "case" || screen === "decision") && detail && caseHydration.caseId === selectedCaseId && (caseHydration.advisoryPending || caseHydration.replayPending)
        ? <CaseContextHydration advisoryPending={caseHydration.advisoryPending} replayPending={caseHydration.replayPending} />
        : null}
      {workSurface}
    </main>
    {workbench.layout.rightOpen ? <WorkbenchResizeHandle side="right" width={workbench.layout.rightWidth} onBegin={workbench.beginResize} onMove={workbench.moveResize} onEnd={workbench.endResize} onKeyboardResize={workbench.keyboardResize} onReset={workbench.resetWidth} /> : null}
    {workbench.isDesktop ? <button type="button" className="pane-edge-trigger pane-edge-trigger--right" aria-label="Open inspector pane" aria-expanded={workbench.rightVisible} onMouseEnter={() => workbench.previewPane("right")} onFocus={() => workbench.previewPane("right")} onClick={() => workbench.previewPane("right")}><span>Inspector</span></button> : null}
    <div className={`${workbench.rightVisible ? "evidence-inspector-slot" : "evidence-inspector-slot is-collapsed"}${workbench.isDesktop && !workbench.layout.rightOpen ? " is-overlay" : ""}`} aria-hidden={!workbench.rightVisible} onMouseEnter={() => workbench.previewPane("right")} onMouseLeave={() => workbench.dismissPane("right")}>
      {workbench.rightVisible ? <><div className="pane-pin-toolbar"><button type="button" aria-label={workbench.layout.rightOpen ? "Unpin inspector pane" : "Pin inspector pane"} aria-pressed={workbench.layout.rightOpen} onClick={() => workbench.togglePin("right")}><span aria-hidden="true">{workbench.layout.rightOpen ? "↦" : "⌖"}</span>{workbench.layout.rightOpen ? "Unpin inspector" : "Pin inspector"}</button></div><EvidenceInspector selectedCase={detail?.case ?? selectedCase} selectedPacket={selectedPacket} projection={overview.projection} sourceTimestamp={overview.source_timestamp} selectedStep={selectedStep} selectedEvidenceNode={selectedEvidenceNode} /></> : null}
    </div>
  </div>;
}

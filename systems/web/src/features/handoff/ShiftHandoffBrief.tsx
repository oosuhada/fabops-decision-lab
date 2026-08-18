import type {DecisionCockpitResponse, OverviewResponse, ReplayResponse} from "../../types";
import {buildShiftHandoffSnapshot} from "./shiftHandoffModel";

export function ShiftHandoffBrief({cockpit, overview, replay}: {cockpit: DecisionCockpitResponse; overview: OverviewResponse; replay: ReplayResponse}) {
  const snapshot = buildShiftHandoffSnapshot(cockpit, overview, replay);
  return <div className="screen-stack shift-handoff">
    <section className="shift-handoff-hero">
      <div><span className="eyebrow">Shift handoff brief</span><h1>What the next engineer must verify first</h1><p>Deterministic snapshot of unresolved decision packets. The source timestamp is preserved exactly; FabOps does not invent a handoff event time or claim a historical reconstruction.</p></div>
      <div className="shift-handoff-source"><span>Source snapshot</span><strong>{snapshot.sourceTimestamp}</strong><small>base {snapshot.releaseVersion} · projection {snapshot.projection.version}</small></div>
    </section>
    <section className="shift-handoff-summary">
      <div><span>Open decisions</span><strong>{snapshot.summary.openDecisions}</strong><small>current packet set</small></div>
      <div><span>High priority</span><strong>{snapshot.summary.highPriority}</strong><small>review first</small></div>
      <div><span>Verify data</span><strong>{snapshot.summary.verifyData}</strong><small>avoid premature fab action</small></div>
      <div><span>Contested RCA</span><strong>{snapshot.summary.contestedHypotheses}</strong><small>explicit counter-evidence</small></div>
      <div><span>Uncertainties</span><strong>{snapshot.summary.explicitUncertainties}</strong><small>recorded items</small></div>
    </section>
    {snapshot.projection.stale ? <section className="panel shift-handoff-alert"><strong>RCA projection is stale</strong><p>{snapshot.projection.lagEvents} authoritative source events have not reached the current RCA/read projection. Treat RCA-derived fields as stale until the projection catches up.</p></section> : null}
    <section className="panel shift-handoff-list">
      <header><div><span className="eyebrow">Unresolved queue</span><h2>Pass these decisions forward in this order</h2></div><small>existing priority rank · no LLM reranking</small></header>
      <ol>{snapshot.items.map((item, index) => <li key={item.caseId}>
        <div className="shift-handoff-rank"><span>{String(index + 1).padStart(2, "0")}</span><b>{item.priorityBand}</b></div>
        <div className="shift-handoff-decision"><span>{item.lotId} · {item.caseId}</span><strong>{item.decisionQuestion}</strong><small>{item.classification.replaceAll("_", " ")}</small></div>
        <div className="shift-handoff-evidence"><span>Top hypothesis</span><strong>{item.topCandidateId ?? "Unranked"}</strong><small>{item.rcaScore == null ? "No ranker score" : `score ${item.rcaScore.toFixed(2)} (not probability)`} · {item.contradictCount} contradict · {item.supportCount} support</small></div>
        <div className="shift-handoff-next"><span>Current recommendation</span><strong>{item.recommendationLabel}</strong><small>{item.humanApprovalRequired ? "Human approval required" : "Evidence / diagnostic step"} · {item.uncertaintyCount} uncertainties</small></div>
      </li>)}</ol>
    </section>
    <section className="shift-handoff-boundaries">{snapshot.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</section>
  </div>;
}


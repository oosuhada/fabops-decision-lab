import type {DecisionPacket, RcaCandidate} from "../../types";

const COMPONENT_LABELS: Record<string, string> = {
  temporal_proximity: "Temporal proximity",
  affected_scope_overlap: "Affected scope overlap",
  chamber_specific_deviation: "Chamber-specific deviation",
  change_or_maintenance: "Change / maintenance",
  defect_pattern_compatibility: "Defect-pattern compatibility",
  contradicting_evidence: "Contradicting evidence",
};

function componentEntries(candidate: RcaCandidate) {
  return Object.entries(candidate.score_components).map(([id, value]) => ({id, value, signed: id === "contradicting_evidence" ? -value : value}));
}

export function RcaExplainability({candidates}: {candidates: RcaCandidate[]}) {
  const top = candidates[0];
  if (!top) return null;
  const components = componentEntries(top);
  const reconstructed = Number(components.reduce((sum, item) => sum + item.signed, 0).toFixed(5));
  const maximum = Math.max(...components.map((item) => Math.abs(item.signed)), .01);
  return <section className="panel rca-explainability">
    <header><div><span className="eyebrow">Faithful RCA explanation</span><h2>Why is #{top.candidate_id} ranked first?</h2></div><div className="rca-faithfulness"><strong>{reconstructed === top.score ? "RECONSTRUCTED" : "CHECK REQUIRED"}</strong><small>score ≠ probability</small></div></header>
    <div className="rca-explainability-grid">
      <div className="rca-component-list">
        {components.map((component) => <div key={component.id} className={component.signed < 0 ? "is-contradict" : component.signed > 0 ? "is-support" : "is-neutral"}>
          <span>{COMPONENT_LABELS[component.id] ?? component.id.replaceAll("_", " ")}</span>
          <i><b style={{width: `${Math.max(2, Math.abs(component.signed) / maximum * 100)}%`}} /></i>
          <strong>{component.signed >= 0 ? "+" : ""}{component.signed.toFixed(2)}</strong>
        </div>)}
        <footer><span>Reconstructed deterministic score</span><strong>{reconstructed.toFixed(2)}</strong><small>reported {top.score.toFixed(2)}</small></footer>
      </div>
      <div className="rca-alternative-list">
        <span className="eyebrow">Alternative candidates</span>
        {candidates.map((candidate, index) => <article key={candidate.candidate_id} className={index === 0 ? "is-top" : ""}>
          <div><span>#{index + 1}</span><strong>{candidate.candidate_id}</strong></div>
          <b>{candidate.score.toFixed(2)}</b>
          <small>{candidate.supporting_evidence.length} support · {candidate.contradicting_evidence.length} contradict</small>
        </article>)}
      </div>
    </div>
    <p className="rca-explanation-note">The bars above are the exact additive terms used by the deterministic ranker. They are not learned feature importance, calibrated probability, or LLM-generated confidence.</p>
  </section>;
}

export function DecisionBoundaryPanel({packet}: {packet: DecisionPacket}) {
  const boundary = packet.decision_boundary;
  if (!boundary) return null;
  const target = packet.options.find((option) => option.option_id === boundary.target_option_id);
  return <section className="panel decision-boundary-panel">
    <header><div><span className="eyebrow">What would change my mind?</span><h2>Deterministic recommendation boundary</h2></div><span className={boundary.all_conditions_met ? "boundary-state is-met" : "boundary-state"}>{boundary.all_conditions_met ? "BOUNDARY MET" : "MORE EVIDENCE"}</span></header>
    <div className="decision-boundary-summary"><div><span>Current recommendation</span><strong>{packet.options.find((option) => option.option_id === packet.recommended_option_id)?.label ?? packet.recommended_option_id}</strong></div><div><span>Boundary target</span><strong>{target?.label ?? boundary.target_option_id}</strong></div></div>
    <ol className="decision-boundary-conditions">{boundary.conditions.map((condition) => <li key={condition.condition_id} className={`is-${condition.status}`}>
      <span className="boundary-condition-state">{condition.status === "met" ? "✓" : condition.status === "unmet" ? "×" : "?"}</span>
      <div><strong>{condition.label}</strong><small>current: {String(condition.current_value ?? "unknown")} · required: {condition.required}</small><code>{condition.evidence_refs.join(" · ")}</code></div>
    </li>)}</ol>
    <footer><strong>Confidence is not probability.</strong><span>{boundary.policy_statement}</span></footer>
  </section>;
}


import type {ProjectionStatus} from "../../types";

export function AuthorityChain({projection}: {projection: ProjectionStatus | null}) {
  const stages = [
    {id: "source", label: "Authoritative source", owner: "PostgreSQL / event log", role: "Observed operational facts"},
    {id: "deterministic", label: "Deterministic computation", owner: "SPC / RCA services", role: "Classification, score, recommendation"},
    {id: "projection", label: "Rebuildable projection", owner: "Persistent read model", role: projection?.stale ? `STALE · ${projection.lag_events} events` : `Current read projection${projection?.slo_state ? ` · SLO ${projection.slo_state}` : ""}`},
    {id: "advisory", label: "System advisory", owner: "Evidence-grounded logic", role: "Proposal only · no mutation authority"},
    {id: "wording", label: "AI wording", owner: "Bounded PresentationSpec", role: "Wording only · recommendation immutable"},
    {id: "human", label: "Human authority", owner: "Yield / Process Engineer", role: "Approve, reject, request evidence"},
    {id: "audit", label: "Append-only audit", owner: "Decision ledger", role: "Replayable decision record"},
  ];
  return <section className="authority-chain" aria-label="Decision authority chain">
    <header><div><span className="eyebrow">Authority boundary</span><strong>Source → computation → projection → advisory → human → audit</strong></div><b>NO EQUIPMENT CONTROL</b></header>
    <ol>{stages.map((stage, index) => <li key={stage.id} className={`authority-stage authority-stage--${stage.id}`}>
      <span>{String(index + 1).padStart(2, "0")}</span>
      <div><strong>{stage.label}</strong><b>{stage.owner}</b><small>{stage.role}</small></div>
    </li>)}</ol>
  </section>;
}

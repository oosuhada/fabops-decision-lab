import {useMemo, useState} from "react";
import type {DecisionPacket} from "../../types";
import {compareDecisionPackets} from "./caseComparisonModel";

function PacketCard({packet, side}: {packet: DecisionPacket; side: "A" | "B"}) {
  const candidate = packet.evidence.top_candidate;
  const option = packet.options.find((item) => item.option_id === packet.recommended_option_id);
  return <article className="case-comparison-card">
    <header><span>CASE {side}</span><strong>{packet.lot_id}</strong><small>{packet.case_id}</small></header>
    <div><span>Decision question</span><strong>{packet.decision_question}</strong></div>
    <div><span>Top hypothesis</span><strong>{candidate?.candidate_id ?? "Unranked"}</strong><small>{candidate ? `score ${candidate.score.toFixed(2)} · ${candidate.supporting_evidence.length} support · ${candidate.contradicting_evidence.length} contradict` : "No deterministic RCA candidate"}</small></div>
    <div><span>Current recommendation</span><strong>{option?.label ?? packet.recommended_option_id}</strong><small>{packet.recommended_option_id}</small></div>
  </article>;
}

function RefList({title, refs}: {title: string; refs: string[]}) {
  return <div className="case-comparison-refs__column"><strong>{title}</strong><span>{refs.length} refs</span>{refs.length ? <ul>{refs.map((reference) => <li key={reference}>{reference}</li>)}</ul> : <p>None in the current packet snapshots.</p>}</div>;
}

export function CaseComparisonWorkbench({packets}: {packets: DecisionPacket[]}) {
  const leftDefault = packets[0]?.case_id ?? "";
  const rightDefault = packets.find((packet) => packet.case_id !== leftDefault)?.case_id ?? leftDefault;
  const [leftCaseId, setLeftCaseId] = useState(leftDefault);
  const [rightCaseId, setRightCaseId] = useState(rightDefault);
  const left = packets.find((packet) => packet.case_id === leftCaseId) ?? packets[0] ?? null;
  const right = packets.find((packet) => packet.case_id === rightCaseId) ?? packets.find((packet) => packet.case_id !== left?.case_id) ?? null;
  const comparison = useMemo(() => left && right && left.case_id !== right.case_id ? compareDecisionPackets(left, right) : null, [left, right]);

  if (packets.length < 2) {
    return <div className="screen-stack"><section className="panel case-comparison-empty"><span className="eyebrow">Case comparison</span><h1>Two real case packets are required</h1><p>FabOps will not fabricate a baseline or duplicate the same case to manufacture a comparison.</p></section></div>;
  }

  return <div className="screen-stack case-comparison-workbench">
    <section className="case-comparison-hero">
      <div><span className="eyebrow">Case comparison workbench</span><h1>Compare evidence posture, not opaque AI opinions</h1><p>Side-by-side comparison uses current deterministic decision-packet snapshots only. It does not create a historical baseline, change RCA ranking, or alter human decision authority.</p></div>
      <div className="case-comparison-controls">
        <label><span>Case A</span><select value={left?.case_id ?? ""} onChange={(event) => setLeftCaseId(event.target.value)}>{packets.map((packet) => <option key={packet.case_id} value={packet.case_id}>{packet.lot_id} · {packet.case_id}</option>)}</select></label>
        <label><span>Case B</span><select value={right?.case_id ?? ""} onChange={(event) => setRightCaseId(event.target.value)}>{packets.map((packet) => <option key={packet.case_id} value={packet.case_id} disabled={packet.case_id === left?.case_id}>{packet.lot_id} · {packet.case_id}</option>)}</select></label>
      </div>
    </section>

    {left && right && comparison ? <>
      <section className="case-comparison-pair"><PacketCard packet={left} side="A" /><PacketCard packet={right} side="B" /></section>
      <section className="panel case-comparison-matrix">
        <header><div><span className="eyebrow">Deterministic packet diff</span><h2>What is materially different?</h2></div><small>{comparison.sameClassification ? "same classification" : "different classifications"} · {comparison.sameRecommendation ? "same recommendation" : "different recommendations"}</small></header>
        <div className="table-scroll"><table><thead><tr><th>Metric</th><th>Case A</th><th>Case B</th><th>Interpretation boundary</th></tr></thead><tbody>{comparison.rows.map((row) => <tr key={row.metric} data-direction={row.direction}><td><strong>{row.metric}</strong></td><td>{row.left}</td><td>{row.right}</td><td><small>{row.semantics}</small></td></tr>)}</tbody></table></div>
      </section>
      <section className="panel case-comparison-refs">
        <header><div><span className="eyebrow">Provenance identity diff</span><h2>Which grounded references overlap?</h2></div><small>Exact reference IDs only · no inferred equivalence</small></header>
        <div className="case-comparison-refs__grid"><RefList title="Shared" refs={comparison.sharedEvidenceRefs} /><RefList title="Case A only" refs={comparison.leftOnlyEvidenceRefs} /><RefList title="Case B only" refs={comparison.rightOnlyEvidenceRefs} /></div>
      </section>
    </> : <section className="panel case-comparison-empty"><strong>Select two different cases</strong><p>The same case cannot be used as both sides of a comparison.</p></section>}
  </div>;
}


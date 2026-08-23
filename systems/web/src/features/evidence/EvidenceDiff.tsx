import {useMemo, useState} from "react";
import type {RcaCandidate} from "../../types";
import {buildCandidateEvidenceDiff} from "./evidenceDiffModel";

function readableEvidence(record: Record<string, unknown>) {
  const entries = Object.entries(record).filter(([, value]) => value != null).slice(0, 4);
  return entries.length
    ? entries.map(([key, value]) => `${key.replaceAll("_", " ")}: ${Array.isArray(value) ? value.join(", ") : String(value)}`).join(" · ")
    : "Evidence record";
}

function EvidenceDiffBucket({title, items, tone}: {title: string; items: Array<Record<string, unknown>>; tone: "shared" | "left" | "right"}) {
  return <div className={`evidence-diff-bucket evidence-diff-bucket--${tone}`}>
    <h4>{title} <span>{items.length}</span></h4>
    {items.length ? <ul>{items.map((item, index) => <li key={`${tone}-${index}`}>{readableEvidence(item)}</li>)}</ul> : <p>None in the source-linked candidate evidence.</p>}
  </div>;
}

export function EvidenceDiff({candidates}: {candidates: RcaCandidate[]}) {
  const [leftId, setLeftId] = useState(candidates[0]?.candidate_id ?? "");
  const [rightId, setRightId] = useState(candidates[1]?.candidate_id ?? "");
  const left = candidates.find((candidate) => candidate.candidate_id === leftId) ?? candidates[0] ?? null;
  const rightFallback = candidates.find((candidate) => candidate.candidate_id !== left?.candidate_id) ?? null;
  const right = candidates.find((candidate) => candidate.candidate_id === rightId && candidate.candidate_id !== left?.candidate_id) ?? rightFallback;
  const diff = useMemo(() => left && right ? buildCandidateEvidenceDiff(left, right) : null, [left, right]);

  return <section className="panel evidence-diff-panel">
    <header>
      <div><span className="eyebrow">Evidence diff</span><h2>Which evidence separates competing hypotheses?</h2></div>
      <small>Source-linked candidate evidence only · no fabricated baseline</small>
    </header>
    {!left ? <div className="evidence-diff-empty"><strong>No RCA candidate</strong><p>The deterministic RCA projection did not produce a candidate to compare.</p></div> : !right || !diff ? <div className="evidence-diff-empty"><strong>No alternate candidate available</strong><p>This case has one deterministic RCA candidate. FabOps does not invent a comparison candidate.</p></div> : <>
      <div className="evidence-diff-controls">
        <label>Candidate A<select aria-label="Evidence diff candidate A" value={left.candidate_id} onChange={(event) => setLeftId(event.target.value)}>{candidates.map((candidate) => <option key={candidate.candidate_id} value={candidate.candidate_id}>{candidate.candidate_id}</option>)}</select></label>
        <span>vs</span>
        <label>Candidate B<select aria-label="Evidence diff candidate B" value={right.candidate_id} onChange={(event) => setRightId(event.target.value)}>{candidates.filter((candidate) => candidate.candidate_id !== left.candidate_id).map((candidate) => <option key={candidate.candidate_id} value={candidate.candidate_id}>{candidate.candidate_id}</option>)}</select></label>
      </div>
      <div className="evidence-diff-summary">
        <div><span>Candidate A score</span><strong>{left.score.toFixed(2)}</strong><small>{left.supporting_evidence.length} support · {left.contradicting_evidence.length} contradict</small></div>
        <div><span>Score delta A − B</span><strong>{diff.scoreDelta >= 0 ? "+" : ""}{diff.scoreDelta.toFixed(2)}</strong><small>deterministic ranker score, not probability</small></div>
        <div><span>Candidate B score</span><strong>{right.score.toFixed(2)}</strong><small>{right.supporting_evidence.length} support · {right.contradicting_evidence.length} contradict</small></div>
      </div>
      <div className="evidence-diff-components">
        <h3>Score component delta</h3>
        <div className="table-scroll"><table><thead><tr><th>Component</th><th>A</th><th>B</th><th>A − B</th></tr></thead><tbody>{diff.components.map((item) => <tr key={item.component}><td>{item.component.replaceAll("_", " ")}</td><td>{item.left.toFixed(2)}</td><td>{item.right.toFixed(2)}</td><td>{item.delta >= 0 ? "+" : ""}{item.delta.toFixed(2)}</td></tr>)}</tbody></table></div>
      </div>
      <div className="evidence-diff-section">
        <div className="evidence-diff-section__head"><span>Supporting evidence</span><strong>{diff.support.shared.length} shared · {diff.support.leftOnly.length} A-only · {diff.support.rightOnly.length} B-only</strong></div>
        <div className="evidence-diff-grid">
          <EvidenceDiffBucket title="Shared" tone="shared" items={diff.support.shared.map((pair) => pair.left)} />
          <EvidenceDiffBucket title="A only" tone="left" items={diff.support.leftOnly} />
          <EvidenceDiffBucket title="B only" tone="right" items={diff.support.rightOnly} />
        </div>
      </div>
      <div className="evidence-diff-section evidence-diff-section--contradict">
        <div className="evidence-diff-section__head"><span>Contradicting evidence</span><strong>{diff.contradict.shared.length} shared · {diff.contradict.leftOnly.length} A-only · {diff.contradict.rightOnly.length} B-only</strong></div>
        <div className="evidence-diff-grid">
          <EvidenceDiffBucket title="Shared" tone="shared" items={diff.contradict.shared.map((pair) => pair.left)} />
          <EvidenceDiffBucket title="A only" tone="left" items={diff.contradict.leftOnly} />
          <EvidenceDiffBucket title="B only" tone="right" items={diff.contradict.rightOnly} />
        </div>
      </div>
      <p className="evidence-diff-note">Diff changes inspection visibility only. It does not alter the deterministic RCA score, candidate order, recommendation, or workflow state.</p>
    </>}
  </section>;
}

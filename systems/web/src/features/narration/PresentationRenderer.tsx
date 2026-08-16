import type {DecisionBriefResponse} from "../../types";

type PresentationSpec = NonNullable<DecisionBriefResponse["brief"]["presentation"]>;
type PresentationBlock = PresentationSpec["blocks"][number];

function EvidenceRefs({refs}: {refs: string[]}) {
  return <small className="presentation-evidence-refs">Evidence: {refs.join(" · ") || "none"}</small>;
}

function PresentationBlockView({block}: {block: PresentationBlock}) {
  if (block.type === "SummaryCard") {
    return <article className="presentation-block presentation-block--summary"><span className="presentation-block__type">SummaryCard</span><h3>{block.title}</h3><p>{block.body}</p><EvidenceRefs refs={block.evidence_refs} /></article>;
  }
  if (block.type === "ComparisonCard") {
    return <article className="presentation-block presentation-block--comparison"><span className="presentation-block__type">ComparisonCard</span><h3>{block.title}</h3><div className="presentation-options">{(block.options ?? []).map((option) => <div key={option.option_id} className={option.option_id === block.recommended_option_id ? "is-recommended" : ""}><span>{option.stance}</span><strong>{option.label}</strong><p>{option.tradeoff}</p><small>{option.requires_human_approval ? "human approval required" : "evidence collection only"}</small></div>)}</div><EvidenceRefs refs={block.evidence_refs} /></article>;
  }
  if (block.type === "Checklist") {
    return <article className="presentation-block presentation-block--checklist"><span className="presentation-block__type">Checklist</span><h3>{block.title}</h3><ol>{(block.items ?? []).map((item, index) => <li key={`${item.label}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.label}</strong><p>{item.detail}</p><small>{item.evidence_refs.join(" · ")}</small></div></li>)}</ol><EvidenceRefs refs={block.evidence_refs} /></article>;
  }
  if (block.type === "EvidenceTable") {
    return <article className="presentation-block presentation-block--evidence"><span className="presentation-block__type">EvidenceTable</span><h3>{block.title}</h3><div className="presentation-evidence-table">{(block.rows ?? []).length ? (block.rows ?? []).map((row) => <div key={`${row.kind}-${row.record_index}`} className={`is-${row.kind}`}><span>{row.kind.toUpperCase()}</span><strong>{row.summary}</strong><small>record {row.record_index + 1}</small></div>) : <p>No explicit support/contradiction rows are attached to the top candidate.</p>}</div><EvidenceRefs refs={block.evidence_refs} /></article>;
  }
  return <article className="presentation-block presentation-block--unsupported"><span className="presentation-block__type">{block.type}</span><h3>{block.title}</h3><p>This known block type is allowed by the server schema but is not enabled in the current FabOps renderer.</p><EvidenceRefs refs={block.evidence_refs} /></article>;
}

export function PresentationRenderer({spec}: {spec: PresentationSpec}) {
  return <section className="bounded-presentation" aria-label="Bounded AI presentation">
    <header><div><span className="eyebrow">Validated presentation spec</span><strong>{spec.intent.replaceAll("_", " ")}</strong></div><div><span>{spec.schema_version}</span><strong>KNOWN COMPONENTS ONLY</strong><small>{spec.execution_capabilities.length} execution capabilities</small></div></header>
    <div className="bounded-presentation__blocks">{spec.blocks.map((block, index) => <PresentationBlockView key={`${block.type}-${index}`} block={block} />)}</div>
  </section>;
}

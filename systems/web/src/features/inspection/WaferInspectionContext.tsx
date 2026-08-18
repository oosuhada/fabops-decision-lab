import {scaleLinear} from "d3";
import type {InspectionPoint} from "../../types";

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function WaferInspectionContext({inspections}: {inspections: InspectionPoint[]}) {
  const ordered = [...inspections].sort((left, right) => left.event_time.localeCompare(right.event_time) || left.inspection_id.localeCompare(right.inspection_id));
  const x = scaleLinear().domain([0, 1]).range([0, 100]).clamp(true);

  return <section className="wafer-inspection-context" aria-label="Wafer inspection context">
    <header>
      <div><span className="eyebrow">Wafer inspection context</span><strong>Source-backed inspection evidence</strong></div>
      <span className="wafer-spatial-gap">Spatial die coordinates unavailable in current API</span>
    </header>
    <div className="wafer-inspection-layout">
      <div className="wafer-outline" role="img" aria-label="Wafer outline indicating that no die coordinates are rendered">
        <svg viewBox="0 0 220 220" aria-hidden="true">
          <circle cx="110" cy="106" r="82" />
          <path d="M 88 187 L 132 187" />
          <line x1="110" y1="24" x2="110" y2="188" />
          <line x1="28" y1="106" x2="192" y2="106" />
        </svg>
        <div><strong>{ordered.length}</strong><span>inspection records</span><small>No spatial die marks rendered</small></div>
      </div>
      <div className="wafer-inspection-records">
        {ordered.length ? ordered.map((inspection) => <article key={inspection.inspection_id}>
          <div className="wafer-inspection-record__identity">
            <span>{inspection.wafer_id}</span>
            <strong>{inspection.defect_pattern}</strong>
            <small>{inspection.inspection_id}</small>
          </div>
          <div className="wafer-inspection-record__metric">
            <div><span>Yield</span><strong>{formatPercent(inspection.yield)}</strong></div>
            <div className="wafer-quantitative-track" aria-label={`Yield ${formatPercent(inspection.yield)}`}><i style={{width: `${x(inspection.yield)}%`}} /></div>
          </div>
          <div className="wafer-inspection-record__metric wafer-inspection-record__metric--failure">
            <div><span>Failed die ratio</span><strong>{formatPercent(inspection.failed_die_ratio)}</strong></div>
            <div className="wafer-quantitative-track" aria-label={`Failed die ratio ${formatPercent(inspection.failed_die_ratio)}`}><i style={{width: `${x(inspection.failed_die_ratio)}%`}} /></div>
          </div>
          <dl>
            <div><dt>Pattern provenance</dt><dd>{inspection.pattern_provenance}</dd></div>
            <div><dt>Observed at</dt><dd>{inspection.event_time}</dd></div>
          </dl>
        </article>) : <div className="wafer-inspection-empty"><strong>No wafer inspection records in this case</strong><p>No geometry, zones, or affected die locations are inferred from missing source data.</p></div>}
      </div>
    </div>
    <footer>Wafer geometry is used only as an inspection container. Bar position is quantitative yield/failure magnitude, not physical die location.</footer>
  </section>;
}

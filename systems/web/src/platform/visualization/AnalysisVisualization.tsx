import type {MeasurementPoint} from "../../types";
import {validateVisualizationSpec, type VisualizationSpec} from "./registry";

function mean(points: MeasurementPoint[]) {
  return points.length ? points.reduce((sum, point) => sum + point.value, 0) / points.length : 0;
}

function groupMeans(points: MeasurementPoint[], channel: "chamber_id" | "sensor_name" | "step_id") {
  const groups = new Map<string, number[]>();
  for (const point of points) groups.set(point[channel], [...(groups.get(point[channel]) ?? []), point.value]);
  return Array.from(groups, ([key, values]) => ({key, value: values.reduce((sum, item) => sum + item, 0) / values.length, count: values.length}));
}

export function AnalysisVisualization({spec, points}: {spec: VisualizationSpec | null; points: MeasurementPoint[]}) {
  if (!spec) return <div className="analysis-visualization analysis-visualization--empty"><strong>No chart step</strong><p>Add a bounded Chart block to render the current evidence selection.</p></div>;
  const validation = validateVisualizationSpec(spec);
  if (!validation.valid) return <div className="analysis-visualization analysis-visualization--empty"><strong>Visualization rejected</strong><p>{validation.reason}</p></div>;
  if (!points.length) return <div className="analysis-visualization analysis-visualization--empty"><strong>No matching evidence</strong><p>The current bounded filters returned zero measurement records.</p></div>;

  if (spec.type === "table") {
    return <div className="analysis-visualization"><header><span>{spec.title}</span><strong>Evidence table</strong></header><div className="table-scroll"><table><thead><tr><th>Time</th><th>Step</th><th>Chamber</th><th>Sensor</th><th>Value</th><th>Event</th></tr></thead><tbody>{points.slice(0, 60).map((point) => <tr key={point.event_id}><td>{point.event_time}</td><td>{point.step_id}</td><td>{point.chamber_id}</td><td>{point.sensor_name}</td><td>{point.value.toFixed(3)} {point.unit}</td><td><code>{point.event_id.slice(0, 10)}</code></td></tr>)}</tbody></table></div></div>;
  }

  if (spec.type === "metric") {
    return <div className="analysis-visualization analysis-visualization--metric"><header><span>{spec.title}</span><strong>Bounded aggregate</strong></header><div><strong>{spec.y === "count" ? points.length : mean(points).toFixed(3)}</strong><span>{spec.y === "count" ? "evidence records" : "mean selected value"}</span></div><p>This is a descriptive analysis value, not a confidence/probability score.</p></div>;
  }

  if (spec.type === "histogram") {
    const values = points.map((point) => point.value);
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = Math.max(.000001, maximum - minimum);
    const bucketCount = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(values.length))));
    const buckets = Array.from({length: bucketCount}, () => 0);
    values.forEach((value) => {buckets[Math.min(bucketCount - 1, Math.floor(((value - minimum) / span) * bucketCount))] += 1;});
    const maxBucket = Math.max(...buckets, 1);
    return <div className="analysis-visualization"><header><span>{spec.title}</span><strong>Distribution</strong></header><div className="analysis-histogram">{buckets.map((count, index) => <div key={index}><span style={{height: `${Math.max(6, (count / maxBucket) * 100)}%`}}><i>{count}</i></span></div>)}</div><footer><span>{minimum.toFixed(2)}</span><span>{points.length} records</span><span>{maximum.toFixed(2)}</span></footer></div>;
  }

  if (spec.type === "heatmap" || spec.type === "bar" || spec.type === "comparison") {
    const grouping = spec.group_by === "sensor_name" || spec.group_by === "step_id" ? spec.group_by : "chamber_id";
    const groups = groupMeans(points, grouping);
    const maximum = Math.max(...groups.map((group) => Math.abs(group.value)), 1);
    return <div className="analysis-visualization"><header><span>{spec.title}</span><strong>{spec.type === "heatmap" ? "Grouped intensity" : "Grouped comparison"}</strong></header><div className={spec.type === "heatmap" ? "analysis-heatmap" : "analysis-bars"}>{groups.map((group) => spec.type === "heatmap" ? <div key={group.key} style={{"--analysis-intensity": Math.max(.12, Math.abs(group.value) / maximum)} as React.CSSProperties}><span>{group.key}</span><strong>{group.value.toFixed(2)}</strong><small>{group.count} records</small></div> : <div key={group.key}><span>{group.key}</span><i><b style={{width: `${Math.max(4, Math.abs(group.value) / maximum * 100)}%`}} /></i><strong>{group.value.toFixed(2)}</strong></div>)}</div></div>;
  }

  if (spec.type === "timeline") {
    return <div className="analysis-visualization"><header><span>{spec.title}</span><strong>Evidence sequence</strong></header><ol className="analysis-timeline">{[...points].sort((a, b) => a.event_time.localeCompare(b.event_time)).slice(0, 40).map((point) => <li key={point.event_id}><time>{point.event_time}</time><strong>{point.step_id} · {point.sensor_name}</strong><span>{point.chamber_id} · {point.value.toFixed(3)} {point.unit}</span></li>)}</ol></div>;
  }

  if (spec.type === "graph") {
    return <div className="analysis-visualization analysis-visualization--empty"><strong>Graph renderer is governed separately</strong><p>Use Evidence Graph 2.0 for typed projection traversal. Analysis blocks do not create arbitrary graph nodes.</p></div>;
  }

  const sorted = [...points].sort((a, b) => a.event_time.localeCompare(b.event_time));
  const values = sorted.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = Math.max(.000001, maximum - minimum);
  const svgPoints = sorted.map((point, index) => ({x: sorted.length === 1 ? 320 : 28 + index * (584 / (sorted.length - 1)), y: 196 - ((point.value - minimum) / span) * 154, point}));
  return <div className="analysis-visualization"><header><span>{spec.title}</span><strong>Source-linked time series</strong></header><svg viewBox="0 0 640 220" role="img" aria-label={`${points.length} selected measurement points`} preserveAspectRatio="none">{[50, 90, 130, 170].map((y) => <line key={y} x1="28" y1={y} x2="612" y2={y} className="analysis-chart-grid" />)}<polyline points={svgPoints.map((item) => `${item.x},${item.y}`).join(" ")} className="analysis-chart-line" />{svgPoints.map(({x, y, point}) => <circle key={point.event_id} cx={x} cy={y} r="4" className="analysis-chart-point"><title>{`${point.event_time} · ${point.chamber_id} · ${point.value}`}</title></circle>)}</svg><footer><span>{sorted[0]?.event_time}</span><span>{points.length} evidence records</span><span>{sorted.at(-1)?.event_time}</span></footer></div>;
}


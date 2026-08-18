export type VisualizationType = "timeseries" | "histogram" | "bar" | "metric" | "heatmap" | "table" | "timeline" | "graph" | "comparison";

export type VisualizationChannel = "event_time" | "value" | "sensor_name" | "chamber_id" | "step_id" | "count";

export interface VisualizationSpec {
  type: VisualizationType;
  x?: VisualizationChannel;
  y?: VisualizationChannel;
  group_by?: VisualizationChannel;
  title: string;
}

export interface VisualizationDefinition {
  type: VisualizationType;
  label: string;
  intent: "trend" | "distribution" | "comparison" | "summary" | "detail" | "relationship" | "sequence";
  requiredChannels: Array<"x" | "y">;
  allowedChannels: VisualizationChannel[];
  supportsGrouping: boolean;
}

export const VISUALIZATION_REGISTRY: readonly VisualizationDefinition[] = [
  {type: "timeseries", label: "Time series", intent: "trend", requiredChannels: ["x", "y"], allowedChannels: ["event_time", "value", "sensor_name", "chamber_id", "step_id"], supportsGrouping: true},
  {type: "histogram", label: "Histogram", intent: "distribution", requiredChannels: ["x"], allowedChannels: ["value", "sensor_name", "chamber_id", "step_id"], supportsGrouping: true},
  {type: "bar", label: "Bar", intent: "comparison", requiredChannels: ["x", "y"], allowedChannels: ["value", "sensor_name", "chamber_id", "step_id", "count"], supportsGrouping: true},
  {type: "metric", label: "Metric", intent: "summary", requiredChannels: ["y"], allowedChannels: ["value", "count"], supportsGrouping: false},
  {type: "heatmap", label: "Heatmap", intent: "relationship", requiredChannels: ["x", "y"], allowedChannels: ["value", "sensor_name", "chamber_id", "step_id", "count"], supportsGrouping: true},
  {type: "table", label: "Table", intent: "detail", requiredChannels: [], allowedChannels: ["event_time", "value", "sensor_name", "chamber_id", "step_id"], supportsGrouping: false},
  {type: "timeline", label: "Timeline", intent: "sequence", requiredChannels: ["x"], allowedChannels: ["event_time", "sensor_name", "chamber_id", "step_id"], supportsGrouping: true},
  {type: "graph", label: "Graph", intent: "relationship", requiredChannels: [], allowedChannels: [], supportsGrouping: false},
  {type: "comparison", label: "Comparison", intent: "comparison", requiredChannels: ["x", "y"], allowedChannels: ["value", "sensor_name", "chamber_id", "step_id", "count"], supportsGrouping: true},
] as const;

const TYPE_SET = new Set(VISUALIZATION_REGISTRY.map((item) => item.type));
const CHANNEL_SET = new Set<VisualizationChannel>(["event_time", "value", "sensor_name", "chamber_id", "step_id", "count"]);

export function visualizationDefinition(type: VisualizationType) {
  return VISUALIZATION_REGISTRY.find((item) => item.type === type) ?? VISUALIZATION_REGISTRY[5];
}

export function validateVisualizationSpec(spec: VisualizationSpec) {
  if (!TYPE_SET.has(spec.type)) return {valid: false, reason: "unknown_visualization_type"} as const;
  const definition = visualizationDefinition(spec.type);
  if (!spec.title.trim() || spec.title.length > 120) return {valid: false, reason: "invalid_title"} as const;
  if (spec.x && !CHANNEL_SET.has(spec.x)) return {valid: false, reason: "invalid_x_channel"} as const;
  if (spec.y && !CHANNEL_SET.has(spec.y)) return {valid: false, reason: "invalid_y_channel"} as const;
  if (spec.group_by && (!CHANNEL_SET.has(spec.group_by) || !definition.supportsGrouping)) return {valid: false, reason: "invalid_group_channel"} as const;
  if (definition.requiredChannels.includes("x") && !spec.x) return {valid: false, reason: "missing_x_channel"} as const;
  if (definition.requiredChannels.includes("y") && !spec.y) return {valid: false, reason: "missing_y_channel"} as const;
  for (const channel of [spec.x, spec.y, spec.group_by]) {
    if (channel && !definition.allowedChannels.includes(channel)) return {valid: false, reason: "unsupported_channel"} as const;
  }
  return {valid: true, reason: null} as const;
}


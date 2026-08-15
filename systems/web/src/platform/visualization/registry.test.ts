import {describe, expect, it} from "vitest";
import {validateVisualizationSpec, VISUALIZATION_REGISTRY} from "./registry";

describe("bounded visualization registry", () => {
  it("accepts known domain channels and rejects executable or unknown visualization inputs", () => {
    expect(validateVisualizationSpec({type: "timeseries", x: "event_time", y: "value", group_by: "chamber_id", title: "Pressure trend"}).valid).toBe(true);
    expect(validateVisualizationSpec({type: "timeseries", x: "event_time", title: "Missing y"} as never)).toEqual({valid: false, reason: "missing_y_channel"});
    expect(validateVisualizationSpec({type: "javascript", title: "execute"} as never).valid).toBe(false);
  });

  it("keeps the registry finite and explicit", () => {
    expect(VISUALIZATION_REGISTRY.map((item) => item.type)).toEqual(["timeseries", "histogram", "bar", "metric", "heatmap", "table", "timeline", "graph", "comparison"]);
  });
});


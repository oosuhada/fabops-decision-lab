import {describe, expect, it} from "vitest";
import {clampWorkbenchWidth, DEFAULT_WORKBENCH_LAYOUT, parseWorkbenchLayout} from "./workbenchLayout";

describe("workbench layout contract", () => {
  it("clamps persisted pane widths to bounded desktop ranges", () => {
    expect(clampWorkbenchWidth("left", 10)).toBe(196);
    expect(clampWorkbenchWidth("left", 999)).toBe(360);
    expect(clampWorkbenchWidth("right", 10)).toBe(280);
    expect(clampWorkbenchWidth("right", 999)).toBe(460);
  });

  it("recovers safely from invalid storage and preserves collapse state", () => {
    expect(parseWorkbenchLayout("not-json")).toEqual(DEFAULT_WORKBENCH_LAYOUT);
    expect(parseWorkbenchLayout(JSON.stringify({leftWidth: 250, rightWidth: 390, leftOpen: false, rightOpen: true}))).toEqual({leftWidth: 250, rightWidth: 390, leftOpen: false, rightOpen: true});
  });

  it("starts desktop panes unpinned unless the user explicitly persisted a pin", () => {
    expect(parseWorkbenchLayout(null)).toEqual({leftWidth: 232, rightWidth: 336, leftOpen: false, rightOpen: false});
  });
});

export interface WorkbenchLayoutState {
  leftWidth: number;
  rightWidth: number;
  leftOpen: boolean;
  rightOpen: boolean;
}

export const DEFAULT_WORKBENCH_LAYOUT: WorkbenchLayoutState = {
  leftWidth: 232,
  rightWidth: 336,
  leftOpen: false,
  rightOpen: false,
};

export function clampWorkbenchWidth(side: "left" | "right", width: number) {
  const [minimum, maximum] = side === "left" ? [196, 360] : [280, 460];
  return Math.max(minimum, Math.min(maximum, Math.round(width)));
}

export function parseWorkbenchLayout(value: string | null): WorkbenchLayoutState {
  if (!value) return DEFAULT_WORKBENCH_LAYOUT;
  try {
    const parsed = JSON.parse(value) as Partial<WorkbenchLayoutState>;
    return {
      leftWidth: clampWorkbenchWidth("left", Number(parsed.leftWidth) || DEFAULT_WORKBENCH_LAYOUT.leftWidth),
      rightWidth: clampWorkbenchWidth("right", Number(parsed.rightWidth) || DEFAULT_WORKBENCH_LAYOUT.rightWidth),
      leftOpen: parsed.leftOpen === true,
      rightOpen: parsed.rightOpen === true,
    };
  } catch {
    return DEFAULT_WORKBENCH_LAYOUT;
  }
}

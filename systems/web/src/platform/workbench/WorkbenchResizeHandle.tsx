import type {KeyboardEvent, PointerEvent} from "react";

export function WorkbenchResizeHandle({
  side,
  width,
  onBegin,
  onMove,
  onEnd,
  onKeyboardResize,
  onReset,
}: {
  side: "left" | "right";
  width: number;
  onBegin: (side: "left" | "right", event: PointerEvent<HTMLDivElement>) => void;
  onMove: (event: PointerEvent<HTMLDivElement>) => void;
  onEnd: (event: PointerEvent<HTMLDivElement>) => void;
  onKeyboardResize: (side: "left" | "right", event: KeyboardEvent<HTMLDivElement>) => void;
  onReset: (side: "left" | "right") => void;
}) {
  const minimum = side === "left" ? 196 : 280;
  const maximum = side === "left" ? 360 : 460;
  return <div
    className={`workbench-resize-handle workbench-resize-handle--${side}`}
    role="separator"
    tabIndex={0}
    aria-label={`Resize ${side} workbench pane`}
    aria-orientation="vertical"
    aria-valuemin={minimum}
    aria-valuemax={maximum}
    aria-valuenow={width}
    onPointerDown={(event) => onBegin(side, event)}
    onPointerMove={onMove}
    onPointerUp={onEnd}
    onPointerCancel={onEnd}
    onDoubleClick={() => onReset(side)}
    onKeyDown={(event) => onKeyboardResize(side, event)}
  />;
}


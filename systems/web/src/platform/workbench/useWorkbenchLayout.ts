import {useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent} from "react";
import {clampWorkbenchWidth, DEFAULT_WORKBENCH_LAYOUT, parseWorkbenchLayout, type WorkbenchLayoutState} from "./workbenchLayout";

const STORAGE_KEY = "fabops:v08:workbench-layout";

export function useWorkbenchLayout() {
  const [layout, setLayout] = useState<WorkbenchLayoutState>(() => parseWorkbenchLayout(window.localStorage.getItem(STORAGE_KEY)));
  const [preview, setPreview] = useState({left: false, right: false});
  const [isDesktop, setIsDesktop] = useState(() => typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 761px)").matches : true);
  const drag = useRef<{side: "left" | "right"; startX: number; startWidth: number} | null>(null);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  }, [layout]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(min-width: 761px)");
    const update = () => setIsDesktop(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  function setWidth(side: "left" | "right", width: number) {
    setLayout((current) => ({
      ...current,
      [side === "left" ? "leftWidth" : "rightWidth"]: clampWorkbenchWidth(side, width),
    }));
  }

  function beginResize(side: "left" | "right", event: PointerEvent<HTMLDivElement>) {
    drag.current = {side, startX: event.clientX, startWidth: side === "left" ? layout.leftWidth : layout.rightWidth};
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveResize(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const delta = event.clientX - drag.current.startX;
    setWidth(drag.current.side, drag.current.startWidth + (drag.current.side === "left" ? delta : -delta));
  }

  function endResize(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    drag.current = null;
  }

  function keyboardResize(side: "left" | "right", event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const current = side === "left" ? layout.leftWidth : layout.rightWidth;
    setWidth(side, current + direction * (side === "left" ? 16 : -16));
  }

  function resetWidth(side: "left" | "right") {
    setWidth(side, side === "left" ? DEFAULT_WORKBENCH_LAYOUT.leftWidth : DEFAULT_WORKBENCH_LAYOUT.rightWidth);
  }

  function togglePin(side: "left" | "right") {
    const key = side === "left" ? "leftOpen" : "rightOpen";
    setLayout((current) => ({...current, [key]: !current[key]}));
    setPreview((current) => ({...current, [side]: true}));
  }

  function previewPane(side: "left" | "right") {
    setPreview((current) => ({...current, [side]: true}));
  }

  function dismissPane(side: "left" | "right") {
    const pinned = side === "left" ? layout.leftOpen : layout.rightOpen;
    if (!pinned) setPreview((current) => ({...current, [side]: false}));
  }

  const leftVisible = !isDesktop || layout.leftOpen || preview.left;
  const rightVisible = isDesktop && (layout.rightOpen || preview.right);

  const shellStyle = {
    "--workbench-left-width": layout.leftOpen ? `${layout.leftWidth}px` : "0px",
    "--workbench-right-width": layout.rightOpen ? `${layout.rightWidth}px` : "0px",
    "--workbench-left-overlay-width": `${layout.leftWidth}px`,
    "--workbench-right-overlay-width": `${layout.rightWidth}px`,
    "--workbench-left-handle-width": layout.leftOpen ? "5px" : "0px",
    "--workbench-right-handle-width": layout.rightOpen ? "5px" : "0px",
  } as CSSProperties;

  return {layout, shellStyle, isDesktop, leftVisible, rightVisible, beginResize, moveResize, endResize, keyboardResize, resetWidth, togglePin, previewPane, dismissPane};
}

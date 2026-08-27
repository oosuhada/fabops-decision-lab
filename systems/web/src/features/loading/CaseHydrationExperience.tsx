import {useEffect, useMemo, useState} from "react";
import type {ScreenId} from "../../types";

type PreviewKind = "decision" | "case" | "graph" | "analysis";

interface PreviewSlide {
  kind: PreviewKind;
  eyebrow: string;
  title: string;
  copy: string;
  tip: string;
}

const SLIDES: PreviewSlide[] = [
  {
    kind: "decision",
    eyebrow: "DECIDE",
    title: "Decision & Approval",
    copy: "Start with the recommendation, then verify the evidence boundary before any governed action.",
    tip: "Use the right inspector to compare priority, evidence sufficiency, and the current decision trigger.",
  },
  {
    kind: "case",
    eyebrow: "INVESTIGATE",
    title: "Case Investigation",
    copy: "Read the case as a source-linked record: affected scope, measurements, inspection outcome, and RCA candidates.",
    tip: "Open the strongest signal first, then compare supporting and contradicting evidence before escalating.",
  },
  {
    kind: "graph",
    eyebrow: "TRACE",
    title: "Evidence Graph",
    copy: "Follow the lot through process runs, chambers, alarms, measurements, and inspection evidence.",
    tip: "Select a process step to coordinate the graph, evidence lens, and the inspector pane.",
  },
  {
    kind: "analysis",
    eyebrow: "ANALYZE",
    title: "Analysis Workbench",
    copy: "Use aligned trends and comparisons to decide whether a signal is a spike, drift, or repeated regime change.",
    tip: "Look for trajectory changes first; the adaptive visualization is bound to the selected case only.",
  },
];

const SCREEN_KIND: Partial<Record<ScreenId, PreviewKind>> = {
  decision: "decision",
  case: "case",
  graph: "graph",
  analysis: "analysis",
};

function PreviewGraphic({kind}: {kind: PreviewKind}) {
  if (kind === "graph") {
    return <div className="hydration-preview hydration-preview--graph" aria-hidden="true">
      <span className="graph-node graph-node--lot">LOT</span>
      <span className="graph-edge graph-edge--one" />
      <span className="graph-node graph-node--run">RUN</span>
      <span className="graph-edge graph-edge--two" />
      <span className="graph-node graph-node--chamber">CH</span>
      <span className="graph-edge graph-edge--three" />
      <span className="graph-node graph-node--evidence">EV</span>
      <span className="graph-caption">source → process → chamber → evidence</span>
    </div>;
  }
  if (kind === "analysis") {
    return <div className="hydration-preview hydration-preview--analysis" aria-hidden="true">
      <div className="analysis-axis"><span>baseline</span><span>recent</span></div>
      <div className="analysis-bars">
        {[28, 34, 31, 42, 48, 58, 72, 66, 81, 88].map((height, index) => <i key={`${height}-${index}`} style={{height: `${height}%`}} />)}
      </div>
      <div className="analysis-callout"><b>Δ</b><span>trajectory change</span></div>
    </div>;
  }
  if (kind === "case") {
    return <div className="hydration-preview hydration-preview--case" aria-hidden="true">
      <div className="case-preview__header"><span>CASE</span><b>source linked</b></div>
      <div className="case-preview__row"><span>Scope</span><strong>CMP-01-A</strong></div>
      <div className="case-preview__row"><span>Signal</span><strong>pressure drift</strong></div>
      <div className="case-preview__meter"><i /></div>
      <div className="case-preview__evidence"><span /><span /><span /></div>
    </div>;
  }
  return <div className="hydration-preview hydration-preview--decision" aria-hidden="true">
    <div className="decision-preview__top"><span>Decision now</span><b>HIGH</b></div>
    <strong>Verify containment threshold</strong>
    <div className="decision-preview__evidence"><span /><span /><span /></div>
    <div className="decision-preview__footer"><span>Human authority</span><b>Review</b></div>
  </div>;
}

export function CaseHydrationExperience({screen, caseId, lotId, startedAt}: {
  screen: ScreenId;
  caseId: string | null;
  lotId: string | null;
  startedAt: number;
}) {
  const [elapsedMs, setElapsedMs] = useState(() => Math.max(0, Date.now() - startedAt));
  const [manualSlide, setManualSlide] = useState<number | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsedMs(Math.max(0, Date.now() - startedAt)), 120);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const slides = useMemo(() => {
    const preferred = SCREEN_KIND[screen] ?? "decision";
    return [...SLIDES].sort((left, right) => Number(right.kind === preferred) - Number(left.kind === preferred));
  }, [screen]);
  const automaticSlide = Math.floor(elapsedMs / 3200) % slides.length;
  const slideIndex = manualSlide ?? automaticSlide;
  const slide = slides[slideIndex];
  const progress = Math.min(88, Math.round(14 + 74 * (1 - Math.exp(-elapsedMs / 4200))));
  const stage = progress < 34 ? "CASE RECORD" : progress < 66 ? "RCA + EVIDENCE" : "VIEW ASSEMBLY";

  return <section className="case-hydration" aria-live="polite" aria-label="Loading selected case">
    <div className="case-hydration__topline">
      <div><span>SELECTED CASE</span><strong>{lotId ?? caseId ?? "Preparing case"}</strong></div>
      <div className="case-hydration__percent"><span>APPROX.</span><strong>{progress}%</strong></div>
    </div>
    <div className="case-hydration__rail" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label="Approximate case loading progress">
      <i style={{width: `${progress}%`}} />
    </div>
    <div className="case-hydration__grid">
      <div className="case-hydration__copy">
        <span className="eyebrow">{stage}</span>
        <h2>Loading the decision surface, not the whole history.</h2>
        <p>Primary source-linked evidence is loaded first. Advisory and replay context attach after the screen is already usable.</p>
        <div className="case-hydration__steps">
          <div className={progress >= 24 ? "is-ready" : "is-active"}><span>01</span><strong>Case record</strong><small>scope + classification</small></div>
          <div className={progress >= 58 ? "is-ready" : progress >= 24 ? "is-active" : ""}><span>02</span><strong>Evidence</strong><small>RCA + process trace</small></div>
          <div className={progress >= 82 ? "is-active" : ""}><span>03</span><strong>Workbench</strong><small>render selected view</small></div>
        </div>
      </div>
      <div className="case-hydration__tour">
        <div className="case-hydration__preview-frame">
          <div className="case-hydration__preview-head"><span>{slide.eyebrow}</span><b>{slide.title}</b></div>
          <PreviewGraphic kind={slide.kind} />
        </div>
        <div className="case-hydration__tour-copy">
          <strong>{slide.title}</strong>
          <p>{slide.copy}</p>
          <small>{slide.tip}</small>
        </div>
        <div className="case-hydration__dots" role="tablist" aria-label="Loading tips">
          {slides.map((item, index) => <button key={item.kind} type="button" className={index === slideIndex ? "is-active" : ""} aria-label={`Show ${item.title} tip`} aria-selected={index === slideIndex} role="tab" onClick={() => setManualSlide(index)} />)}
        </div>
      </div>
    </div>
  </section>;
}

export function CaseContextHydration({advisoryPending, replayPending}: {advisoryPending: boolean; replayPending: boolean}) {
  const completeCount = Number(!advisoryPending) + Number(!replayPending);
  const progress = 76 + completeCount * 12;
  const detail = advisoryPending && replayPending
    ? "Decision evidence is ready. Advisory and replay are attaching in the background."
    : advisoryPending
      ? "Replay is ready. Advisory context is attaching in the background."
      : "Advisory is ready. Replay context is attaching in the background.";
  return <div className="case-context-hydration" aria-live="polite">
    <span>CONTEXT HYDRATION</span>
    <div className="case-context-hydration__rail"><i style={{width: `${progress}%`}} /></div>
    <strong>{progress}%</strong>
    <small>{detail}</small>
  </div>;
}

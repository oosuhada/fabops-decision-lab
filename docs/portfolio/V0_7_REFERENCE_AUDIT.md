# FabOps v0.7 — reference-driven product audit

This audit records the local reference repositories inspected before the v0.7
workbench upgrade. The goal is pattern extraction, not visual cloning. FabOps
keeps its own domain model, authority boundaries, provenance language, and
release evidence.

## Decision rules used for adaptation

- Prefer **reimplementation** when the reference repository has no clearly
  identified root license or when a pattern is generic enough to express
  independently.
- Prefer **adaptation** only for architectural concepts that can be mapped to
  existing FabOps domain contracts without importing foreign product identity.
- Do not copy Palantir branding, branded assets, proprietary-looking fixtures,
  generic platform scope, or generated demo data.
- PostgreSQL/event state remains authoritative. Neo4j remains a rebuildable RCA
  read projection.
- LLM output remains presentation-only and cannot alter detection, RCA ranking,
  workflow state, authorization, or equipment state.

## Repository audit

| Reference | License observed locally | Most relevant files/modules | Reusable concept | FabOps target | Strategy | Risk | Value / priority |
|---|---|---|---|---|---|---|---|
| BIST Mini (`bist-mini-2-main`) | No root license file found in the inspected tree | `frontend/src/components/feature2/useResearchGap.js`, `frontend/src/components/feature2/pipeline-graph/PipelineGraph.js`, `backend/api/v1/gems/endpoints.py` | long-running workflow status, streaming/polling fallback, pipeline progress, guided research UX | future analysis execution status and bounded narration progress | reimplement only | unclear reuse rights; research UX is broader than FabOps needs | medium / P8+
| Palantir UI/UX clone | No root license file found in the inspected tree | `src/components/foundry/SplitPane.tsx`, `Inspector.tsx`, `WorkbenchToolbar.tsx`, `BoardFrame.tsx`, `src/features/contour/ContourAnalysis.tsx`, `src/features/quiver/ObjectExplorer.tsx`, `TimeSeriesWorkbench.tsx` | real pane resize, contextual inspector, coordinated selection, branchable analysis path, time-series inspection | core workbench, evidence explorer, analysis path | reimplement interaction grammar | brand/IP confusion if copied literally; some demo values are not source-backed | very high / P1
| `team-repos/ontology_dashboard` | No root license file found in the inspected tree | `systems/frontend/src/ui/foundry/ResizableWorkbenchLayout.tsx`, `InspectorTabs.tsx`, `DenseDataTable.tsx`, `ActivityTimeline.tsx`, `features/dashboard/cross-filter-engine.ts`, `features/dashboard/visualization/visualizationRegistry.ts`, `features/analysis/AnalysisPathCanvas.tsx`, `AnalysisGraphProjection.tsx`, `features/agent/EvidenceTraceList.tsx`, `GroundedClaimList.tsx` | persisted workbench geometry, URL/session selection, cross-filter scoping, bounded visualization registry, analysis graph, evidence/claim inspection | FabOps workbench platform layer, typed evidence graph, governed analysis blocks, presentation registry | reimplement/adapt concepts | generic platform abstractions can over-expand FabOps | very high / P0
| Predictive Maintenance ML | MIT | `src/predictive_maintenance/evaluation.py`, `cli.py`, `plotting.py` | validation-only threshold selection, calibration view, bootstrap confidence intervals, slice analysis, expected-cost comparison | Evaluation Lab 2.0 presentation and test discipline | adapt evaluation concepts; no model transplant | metrics can be misleading if applied to FabOps without matching statistical semantics | high / P4
| MaintiQ Predict SPC | No root license file found in inspected project | `src/preprocessing_prediction_engine.py`, `src/open_industrial_validation.py`, `src/create_industrial_engineering_evidence.py`, `src/verify_project.py` | calibration artifacts, threshold evidence, explicit synthetic/sample-data caveats, artifact verification | evaluation evidence UX and release verification | reimplement evidence presentation only | domain mismatch and unclear license | high / P5
| InterpretML | MIT | `python/interpret-core/`, explainer/performance modules referenced by local `CLAUDE.md` | explanation contracts that separate model behavior from UI narration | faithful RCA explanation presentation | concept adaptation | FabOps RCA is deterministic additive scoring, not an ML feature-importance model | medium-high / P5
| OpenGenerativeUI | MIT | local agent/state schema described in `CLAUDE.md`, MCP skill/playbook surfaces | state/schema driven generated presentation | validated FabOps `PresentationSpec` rendered by known components | reimplement bounded schema | arbitrary generated UI would violate FabOps safety boundary | medium-high / P8
| Data Formulator | MIT | repository analysis/workflow surfaces | branchable analytic intent and chart composition | domain-safe analysis path + visualization spec | reimplement domain-safe subset | free-form transforms/code are out of scope | high / P3
| Tremor | root license contains permissive licensing notices; local tree includes MIT/Apache text | component/chart primitives | dense operational metrics and chart composition | visualization renderer ergonomics | concepts only | visual library adoption would add scope/dependency with little domain value | low-medium / later
| Mini Foundry Public | MIT | `backend/app/ontology/object_sets.py`, `backend/app/data/branch_service.py`, architecture review checklist | typed object identity, ObjectSet concept, lifecycle/version context | common FabOps object identity and selection/deep-link contract | adapt concepts only | generic data platform scope is explicitly out of scope | medium / P6
| OpenFoundry Emulator | Apache-2.0 | service/admin API patterns | resource-shaped APIs and paging | only if future object explorer needs server paging | defer | generic platform breadth | low
| Palantir Blueprint | Apache-2.0 | component packages | accessibility/interaction conventions | only generic keyboard/focus expectations | concepts only | branded visual cloning is not a product goal | low
| `ps-genai-agents` | Apache-2.0 | `ps_genai_agents/components/text2cypher/schema.py`, workflow modules | schema-bound graph query planning | optional private read-only graph assistant | defer and redesign | local reference includes configurations where LLM Cypher validation is disabled; unacceptable for FabOps public runtime | medium / optional
| `create-context-graph` | Apache-2.0 | `src/create_context_graph/` schema/fixture structure | typed graph construction and contextual traversal | evidence projection contract | adapt schema concepts | graph must remain projection, never authority | high / P2
| `langgraph-workflow-orchestrator` | MIT | workflow build/test structure | explicit workflow state graph | bounded analysis orchestration where needed | concepts only | unnecessary agent orchestration can obscure deterministic behavior | low-medium
| CodeGraph | MIT | `README.md`, typed structural graph/query flow | typed nodes/edges plus traversal context | Evidence Graph 2.0 typed projection | reimplement domain schema | source project mixes semantic search/LLM extraction, which FabOps does not need | high / P2
| NeoDash | Apache-2.0 | report/selection configuration surfaces | visualization/report registry and selection binding | bounded visualization registry | concept adaptation | arbitrary Cypher/report configuration is out of scope | medium / P4
| python-graph-visualization | GPL family license observed locally | graph visualization packages | graph layout and inspection ideas | evidence graph UX only | no code reuse; reimplement | copyleft compatibility and unnecessary dependency | medium / P2
| yFiles graphs for Streamlit | local license file present; selection/neighborhood behavior documented in `AGENTS.md` | `examples/selection.py`, `examples/neo4j-example.py`, local `AGENTS.md` | synchronized selection, neighborhood expansion, overview/minimap concept, incremental updates | typed evidence graph interactions | concepts only; do not import yFiles code | commercial/licensing constraints and framework mismatch | high concept value / P2

## Highest-value mapping used for implementation

### 1. Resizable decision workbench

`team-repos/ontology_dashboard`
→ `systems/frontend/src/ui/foundry/ResizableWorkbenchLayout.tsx`
→ persisted left/right pane widths, pointer resize, keyboard resize
→ FabOps global navigation / analysis surface / evidence inspector
→ independent React implementation using FabOps class names and storage keys
→ unit test persisted bounds + Playwright keyboard/pointer resize smoke test

`palantir-foundry-uiux-clone`
→ `src/components/foundry/SplitPane.tsx`
→ simple pointer-capture resize interaction
→ FabOps workbench resize behavior
→ interaction concept only
→ E2E resize and responsive fallback

### 2. Evidence Graph 2.0

`CodeGraph`
→ typed structural graph described in `README.md`
→ explicit node/relationship vocabulary instead of decorative graph points
→ `Lot`, `ProcessRun`, `Step`, `Equipment`, `Chamber`, `Measurement`,
  `Inspection`, `Case`, `RCACandidate`, `EvidenceRecord`
→ build graph only from current FabOps case/trace/evidence/RCA payloads
→ projection contract tests + selection/neighbor expansion E2E

`yfiles-graphs-for-streamlit`
→ `examples/selection.py` and neighborhood configuration documented in
  `AGENTS.md`
→ synchronized selection + bounded neighbor expansion
→ FabOps graph selection and inspector coordination
→ framework-independent reimplementation
→ unit tests for deterministic graph projection and neighborhood filtering

### 3. Domain-safe analysis path

`team-repos/ontology_dashboard`
→ `features/analysis/AnalysisPathCanvas.tsx` and boards under
`features/analysis/boards/`
→ typed analysis steps with explicit input/output contracts
→ FabOps-only blocks: Input Case, Filter Step, Filter Chamber, Filter Sensor,
  Time Range, Compare, Group, Aggregate, Chart, Verify Evidence
→ no SQL, no arbitrary code, no mutation
→ deterministic serialization/reload tests and E2E path composition

`palantir-foundry-uiux-clone`
→ `src/features/contour/ContourAnalysis.tsx`
→ branch/copy analysis path interaction
→ FabOps analysis sessions branch from an evidence-inspection point
→ independent state model
→ branch/reload test

### 4. Visualization registry

`team-repos/ontology_dashboard`
→ `features/dashboard/visualization/visualizationRegistry.ts`
→ finite visualization catalog with capability metadata
→ FabOps `VisualizationSpec` accepts only known types and known data channels
→ independently typed registry and validator
→ invalid-spec rejection tests

### 5. Faithful RCA explainability

FabOps source of truth
→ `services/rca/ranking.py`
→ the actual score is additive:
`temporal_proximity + affected_scope_overlap + chamber_specific_deviation + change_or_maintenance + defect_pattern_compatibility - contradicting_evidence`
→ expose those exact score components, never synthetic feature-importance values
→ decision packet + inspector comparison
→ contract test that displayed total reconstructs the ranked score

`InterpretML` and predictive-maintenance references
→ explanation/evaluation presentation discipline
→ distinguish support, contradiction, missing/unknown evidence, and validation
  limitations
→ no transplant of SHAP/probability semantics
→ deterministic output tests

## Explicitly rejected reference patterns

- arbitrary HTML/JavaScript generated by an LLM,
- free-form SQL/Cypher in the public preview,
- LLM-owned graph writes or query validation,
- generic notebook/data-catalog/pipeline-builder platform scope,
- graph nodes invented only for visual density,
- confidence-looking percentages without a defined statistical contract,
- copying Palantir brand assets, typography, colors, or product names.


# Reference Adoption — Semiconductor Forensics

## Decision

FabOps is a high-pressure semiconductor decision workbench, not a cinematic AI dashboard. The reference audit therefore optimizes for deterministic evidence navigation, source/projection boundaries, keyboard-safe interaction, legibility, and bounded motion. Decorative glass, WebGL, 3D, and shader candidates were rejected when they did not encode a source-backed product state.

## Investigated Candidates

| Candidate | Source | License | Intended use | Actual prototype / inspection result | Decision | Final FabOps usage |
|---|---|---|---|---|---|---|
| D3 7.9.0 | https://github.com/d3/d3 | ISC | Deterministic SVG layout and quantitative scales | Five-lane evidence-chain prototype bundled to ~7.7 KB minified / ~3.0 KB gzip for the used scale/shape surface | ADOPT | Graph lane geometry and wafer inspection quantitative scales |
| Motion 13.1.1 | https://github.com/motiondivision/motion | MIT | Precise selected-evidence transition | Full React entry initially pushed the production bundle over the Vite 500 KB warning; `motion/mini` retained the semantic transition while production JS returned below the warning | ADOPT | Evidence Inspector selection transition only; disabled by `prefers-reduced-motion` |
| React Flow / xyflow 12.11.3 | https://github.com/xyflow/xyflow | MIT | Replace custom evidence graph canvas | Same five-node chain prototype bundled to ~177.5 KB minified / ~59.5 KB gzip excluding React; migration would also duplicate working pan/zoom/filter/keyboard semantics | REJECT | Interaction ideas only; no production dependency |
| Cytoscape.js 3.34.1 | https://github.com/cytoscape/cytoscape.js | MIT | Forensic evidence graph renderer | Headless five-node model prototype bundled to ~435.2 KB minified / ~143 KB gzip and still needed a separate DOM accessibility layer | REJECT | Model/relationship ideas only; no production dependency |
| AntV G6 5.1.1 | https://github.com/antvis/G6 | MIT | Rich graph renderer | Package inspection showed a substantially larger runtime surface than required for the existing typed graph; no missing core capability justified migration | REJECT | No shipped usage |
| Graphite | https://github.com/GraphiteEditor/Graphite | Apache-2.0 | Professional node/editor information hierarchy | Interaction/reference review favored explicit ports/layers and inspector hierarchy, but Graphite is an editor application/codebase rather than an appropriate FabOps runtime dependency | REFERENCE | Layer legend, inspector hierarchy, instrument-density principles were reimplemented independently |
| Motion Primitives | https://github.com/ibelick/motion-primitives | MIT | Layout transition patterns | Reference review useful for restrained state changes, but adding a second motion abstraction duplicated Motion itself | REJECT | No code copied; Motion handles the one shipped transition |
| Paper Shaders 0.0.80 | https://github.com/paper-design/shaders | Apache-2.0 | Wafer diffraction material | Package/license inspected; no source-backed spatial state exists for shader-driven wafer effects, so a shader would be decorative | REJECT | No WebGL/shader dependency; fallback not applicable |
| liquid-glass-react 1.1.1 | https://github.com/rdev/liquid-glass-react | MIT | Selected evidence lens / transparency | Package inspected; global refraction would obscure dense evidence and conflict with the forensics direction | REJECT | Semantic transparency implemented with CSS only in selected evidence/projection overlays |
| React Postprocessing 3.1.0 | https://github.com/pmndrs/react-postprocessing | MIT | Bloom / depth / aberration | Requires a 3D/WebGL scene that FabOps neither needs nor can ground in current operational evidence | REJECT | No WebGL dependency |
| Sigma.js | https://github.com/jacomyal/sigma.js | MIT | Large graph rendering | Reference review found it optimized for graph scale/rendering, while current FabOps needs typed DOM/SVG semantics, evidence tables, and deterministic object inspection | REJECT | No shipped usage |

## Prototype Comparison

The three graph prototypes used the same five-stage evidence chain: `source → deterministic → projection → inference → human`.

| Prototype | Result | Product fit |
|---|---:|---|
| A — D3/SVG | ~7.7 KB minified / ~3.0 KB gzip for the used prototype surface | Best fit. Preserves native SVG focus/keyboard handling, current filters, and textual fallback while adding deterministic layout/scales. |
| B — React Flow | ~177.5 KB minified / ~59.5 KB gzip excluding React | Strong general node editor, but would replace already-accepted semantics and add state/runtime surface without improving source truthfulness. |
| C — Cytoscape.js | ~435.2 KB minified / ~143 KB gzip | Powerful graph engine, but too large for the current graph and requires an additional accessibility/semantic layer. |

The prototype directory was `/tmp/fabops-forensics-prototypes`; no rejected prototype code or dependency was copied into production.

## Adopted in Code

| Reference | License | Files / feature used | Changes made | Code copied? | Credit location |
|---|---|---|---|---|---|
| D3 7.9.0 | ISC | `EvidenceGraphExplorer.tsx`, `WaferInspectionContext.tsx` | Uses D3 scales for deterministic lane geometry and quantitative inspection bars while keeping FabOps-owned SVG/DOM renderers | No. Library API used from npm package. | `CREDITS.md` |
| Motion 13.1.1 | MIT | `components.tsx` Evidence Inspector | Uses `motion/mini` for a short selected-evidence transition; explicitly bypassed under reduced-motion preference | No. Library API used from npm package. | `CREDITS.md` |

Both are GREEN because they have permissive licenses, are maintained reusable libraries, materially improve core evidence interaction, do not alter decision authority, and have deterministic/accessibility fallbacks. The final production bundle contains these two libraries and no rejected prototype dependency.

## Visual Principles Adopted

| Reference | Observed principle | FabOps interpretation | Where visible |
|---|---|---|---|
| D3 | Data-bound geometry should encode actual values | Quantitative inspection bars and graph lane placement come from source/model values; no fabricated die positions | Evidence Graph / Wafer Inspection Context |
| Graphite | Professional editors separate canvas, layers, object inspector, and tool authority | Evidence graph exposes source/projection/inference layers and coordinates selection with the right Evidence Inspector | Evidence Graph + global inspector |
| Motion | Motion should explain state change, not decorate idle surfaces | Only selected evidence classification transitions; no ambient panel animation | Evidence Inspector |
| Paper Shaders | Material effects are useful when they encode state | Rejected shader because no spatial wafer state exists; diffraction reduced to limited static accents | Design system only |
| xyflow | Pan/zoom/filter graph exploration should remain direct and predictable | Existing graph gestures retained, plus explicit 1-hop focus and non-SVG relationship fallback | Evidence Graph |

## Glass Reduction

The previous v0.7.1 stylesheet applied `backdrop-filter`, translucent panel backgrounds, gradient blobs, and glass shadows broadly to `.panel`, major headers, hero surfaces, graph cards, and console surfaces. The new canonical `design-system.css`, loaded last, removes blur from generic panels, navigation, heroes, toolbars, charts, option cards, and case surfaces and replaces them with opaque evidence/instrument surfaces.

Transparency remains only where it communicates semantics: the selected Evidence Inspector classification lens uses a restrained translucent overlay so the user can perceive it as a selection/projection layer. Diffraction cyan/violet/amber is limited to authority/layer accents and does not serve as the only severity signal.

## Source Truthfulness

Current API inspection evidence exposes `inspection_id`, `wafer_id`, `yield`, `failed_die_ratio`, `defect_pattern`, `pattern_provenance`, and `event_time`. It does **not** expose die coordinates, wafer zones, affected spatial clusters, or baseline spatial geometry. `WaferInspectionContext` therefore renders a neutral wafer outline, source-backed quantitative bars, provenance, and event time, and explicitly states `Spatial die coordinates unavailable in current API`. No spatial die/zone marks are fabricated.

## Architecture / Authority Boundary

- PostgreSQL / event model remains the authoritative operational source of truth.
- Neo4j remains a rebuildable RCA/read projection.
- Deterministic services own classification, ranking, boundary conditions, and recommendation.
- Bounded AI may only rewrite grounded PresentationSpec wording and cannot change recommendation identity.
- Human users own approval/rejection/evidence-request authority.
- There is no equipment control or equipment execution capability.

## License Verification

- [x] Selected library licenses verified through package metadata and upstream repositories.
- [x] Attribution requirements recorded in `CREDITS.md`.
- [x] No unknown-license code copied.
- [x] No incompatible copyleft dependency introduced.
- [x] Rejected prototype dependencies removed from production.
- [x] No WebGL/shader dependency shipped; WebGL fallback is therefore not applicable.


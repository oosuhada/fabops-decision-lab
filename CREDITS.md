# Third-Party Credits

FabOps Decision Lab uses third-party libraries only where they materially support the governed decision workflow. No reference-project source code was copied into the product during the Semiconductor Forensics redesign.

## Production Dependencies Added by the Forensics Redesign

### D3 7.9.0

- Project: https://github.com/d3/d3
- License: ISC
- FabOps usage: deterministic SVG lane geometry in the typed evidence graph and quantitative scales in Wafer Inspection Context.
- Integration: npm dependency; FabOps-owned React/SVG/DOM components call the public D3 API.

### Motion 13.1.1

- Project: https://github.com/motiondivision/motion
- License: MIT
- FabOps usage: bounded selected-evidence transition in the Evidence Inspector through `motion/mini`.
- Accessibility: the transition is skipped when `prefers-reduced-motion: reduce` is active.
- Integration: npm dependency; no Motion example/component source was copied.

## Reference-Only Sources

Graphite, React Flow/xyflow, Cytoscape.js, AntV G6, Motion Primitives, Paper Shaders, liquid-glass-react, React Postprocessing, Sigma.js, and the other candidates catalogued in `docs/visual-reference-catalog.md` were used only for evaluation or interaction/visual reference unless explicitly listed above as production dependencies. Rejected candidate code is not shipped.

See `docs/reference-adoption.md` for prototype results, rejection rationale, and final usage boundaries.

# UI review baseline — release 0.6.0

This review baseline records the currently deployed release without redesigning
or editing its UI. Screenshots were captured through the public read-only preview
at `https://fabops-preview.oosu.dev` while the M8 burn-in continued.

## Observable review questions

- **Information density:** the desktop overview presents global release status,
  primary navigation, a seven-case object list, a dense case table and the
  evidence inspector at once. Is that density useful to an engineering reviewer,
  or does it slow the portfolio first read?
- **Hierarchy:** the global header, surface heading, metric strip, provenance
  badges and panel headings are all visible hierarchy layers. Which one attracts
  attention first, and is that the intended decision hierarchy?
- **Navigation clarity:** the six workbench destinations are explicit on desktop.
  Is the relationship among Overview → Case → Graph → Decision → Evaluation →
  Replay obvious without prior domain explanation?
- **Selected-object visibility:** case selection is represented in the object
  list, work surface and evidence inspector. Is the currently selected lot/case
  sufficiently persistent while moving between graph and decision screens?
- **Evidence inspector usefulness:** does the persistent inspector reduce context
  switching, or does it compete with the main work surface at 1440/1280 widths?
- **Graph readability:** the Evidence Graph coordinates process lineage, a
  normalized series and an evidence table. Are step/chamber/equipment labels and
  the selected step easy to scan before reading the table?
- **Chart legibility:** the normalized series exposes min/max and point count but
  intentionally stays compact. Is that enough context for a portfolio reviewer to
  understand the signal without mistaking it for a production process chart?
- **Approval workflow clarity:** `PROPOSAL ONLY · NO TOOL CONTROL` and the no-tool
  copy are visible, but the 0.6.0 controls still look actionable. In the current
  public read-only preview their POSTs return `405` by design. Is a future
  read-only/demo-mode banner needed to prevent first-impression confusion?
- **Provenance visibility:** `synthetic`, `inferred`, evaluation provenance and
  release/evidence hashes are present across the flow. Are those labels prominent
  enough to keep the portfolio claim boundary clear?
- **Responsive behavior:** at the captured `390x844` viewport the main overview
  remains usable, while the desktop header-status row containing `RELEASE 0.6.0`
  is hidden by the existing responsive layout. Should release/provenance identity
  remain directly visible on small screens?
- **Empty/error/degraded states:** this healthy-release capture does not exercise
  all empty, error, unauthorized, stale or degraded states. Do those states need a
  separate visual-review pass after the current baseline is approved?
- **Portfolio first impression:** does the first screen communicate
  evidence-grounded yield-excursion triage and the synthetic/no-equipment-control
  boundary before a reviewer gets lost in implementation detail?

No visual changes are selected or implemented by this document. Any UI/UX change
should follow the owner's review of the checked-in screenshots.

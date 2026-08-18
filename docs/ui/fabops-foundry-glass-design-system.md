# FabOps Foundry Glass design system

FabOps v0.7 uses one visual grammar across every screen. The goal is not to
copy Palantir Foundry, but to borrow its disciplined work-surface hierarchy and
combine it with FabOps' liquid-glass identity.

## Reference basis

Local reference material used for this grammar:

- `palantir-foundry-uiux-clone/src/styles/tokens.css`
- `palantir-foundry-uiux-clone/src/styles/app.css`
- `palantir-foundry-uiux-clone/docs/reference/palantir-foundry-contour-quiver-ui-reference.md`
- the locally archived Foundry/Contour/Quiver screen set described by that reference

Repeated Foundry patterns used here are: fixed application chrome, compact
toolbars, a central work surface, an inspector, predictable card insets,
consistent property rows, and a small number of type levels.

## Non-negotiable rules

1. **Spacing is a 4px grid.** Use 4, 8, 12, 16, 20, 24 or 32px. New arbitrary
   7/9/11/13/17px spacing values are not allowed in the canonical layer.
2. **10px is the metadata floor.** 10px is only for labels, badges and chart
   metadata. Normal supporting copy is 11px or larger; working copy is 12px or
   larger.
3. **Panels own their inset.** Standard panel content starts 16px from the
   panel edge. A property row must never touch a panel edge.
4. **Headers share a contract.** Standard panel headers are 56px minimum with
   12px vertical / 16px horizontal padding.
5. **Property rows share a contract.** Desktop rows are at least 44px high,
   use a 132px minimum key column and wrap long values. Mobile rows stack.
6. **Controls are at least 36px high** unless they are compact chart filter
   chips, which may be 32px.
7. **Radius has four levels only:** 6px control, 12px card, 14px panel, 18px
   hero. Pills are reserved for badges/chips.
8. **Glass is hierarchy, not decoration.** Main panels use a restrained glass
   surface; nested data rows use neutral surfaces rather than another blur.
9. **Every route must pass visual geometry gates:** no page-level horizontal
   overflow at 1440px and 390px, consistent panel insets, and no production
   text below the metadata floor.
10. **Semantic state stays visible.** Synthetic/inferred provenance, read-only
    preview, human decision authority and no-tool-control boundaries remain
    visually explicit.

## Canonical tokens

The executable source of truth is `systems/web/src/design-system.css`. It is
loaded after the legacy stylesheet so that new work can migrate incrementally
without reintroducing page-specific visual rules.

## Visual review checklist

- Scan each route at 1440×1000 before reviewing isolated widgets.
- Repeat at 390×844 and confirm no body-level horizontal scroll.
- Check first content inset after every panel header.
- Check that titles, labels, values and metadata map to the defined type scale.
- Check that adjacent cards use the same gap and radius level.
- Check wrapping of hashes, event IDs and provider status strings.
- Check hover/focus, but ensure primary information is visible without hover.
- Re-run route/deep-link tests after any navigation or shell change.

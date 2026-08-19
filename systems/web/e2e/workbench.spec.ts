import {expect, test, type Page} from "@playwright/test";

async function ensureDesktopPanesPinned(page: Page) {
  const controls = page.getByLabel("Workbench pane controls");
  const navigationPin = controls.getByRole("button", {name: "Pin navigation pane"});
  const inspectorPin = controls.getByRole("button", {name: "Pin inspector pane"});
  if (await navigationPin.getAttribute("aria-pressed") === "false") await navigationPin.click();
  if (await inspectorPin.getAttribute("aria-pressed") === "false") await inspectorPin.click();
}

test("decision cockpit connects priority, evidence, grounded brief and governed approval", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  await ensureDesktopPanesPinned(page);
  await expect(page.getByText("NO EQUIPMENT CONTROL").first()).toBeVisible();
  await expect(page.getByText("Resolve before acting")).toBeVisible();
  await expect(page).toHaveURL(/\/DecisionCockpit$/);
  const header = page.locator(".global-header");
  await expect(header.getByText("CANDIDATE BUILD", {exact: true})).toBeVisible();
  await expect(header.getByText("BASE RELEASE", {exact: true})).toBeVisible();
  await expect(page.getByLabel("Section 1, Decide")).toContainText("Ⅰ. Decide");
  await expect(page.getByLabel("Section 2, Investigate")).toContainText("Ⅱ. Investigate");
  await expect(page.getByLabel("Section 3, Trust")).toContainText("Ⅲ. Trust");
  await expect(page.getByLabel("Evidence authority separation")).toContainText("HUMAN DECISION");
  await expect(page.getByRole("heading", {name: "Compare the available stances before acting"})).toBeVisible();
  await expect(page.getByText("Current recommendation").first()).toBeVisible();
  await page.getByRole("button", {name: "Investigate evidence"}).click();
  await expect(page.getByRole("heading", {name: /Is .* the best explanation\?/i})).toBeVisible();
  await expect(page.getByRole("heading", {name: /What supports — and weakens — the hypothesis\?/i})).toBeVisible();

  await page.getByRole("button", {name: /Evidence Graph/i}).click();
  await expect(page).toHaveURL(/\/EvidenceGraph$/);
  await expect(page.getByRole("heading", {name: /lineage/i})).toBeVisible();
  await page.getByRole("button", {name: /ETCH/i}).first().click();
  await expect(page.getByRole("img", {name: /ETCH selected within case-normalized sensor trajectories/i})).toBeVisible();
  await expect(page.getByText("Within-case range position", {exact: true})).toBeVisible();
  await expect(page.getByText("Spatial die coordinates unavailable in current API", {exact: true})).toBeVisible();
  await expect(page.getByText("Accessible relationship fallback", {exact: true})).toBeVisible();
  const signalLegend = page.locator(".signal-legend");
  await expect(signalLegend).toContainText("pressure");
  await expect(signalLegend).toContainText("rf power");
  await expect(signalLegend).toContainText("temperature");
  await expect(signalLegend).toContainText("particle count");
  await expect(page.locator(".signal-series .signal-path")).toHaveCount(4);
  await expect(page.locator(".range-profile__row")).toHaveCount(4);

  await page.getByRole("button", {name: /Decision & Approval/i}).click();
  await expect(page.getByRole("heading", {name: /Should the team/i})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Choose a stance, not an opaque AI answer"})).toBeVisible();
  await expect(page.getByText("NO TOOL CONTROL").last()).toBeVisible();
  await expect(page.getByRole("button", {name: /execute equipment/i})).toHaveCount(0);
  await expect(page.getByText("Grounded decision brief", {exact: true})).toBeVisible();
  await expect(page.getByText("Decision ID preserved", {exact: true})).toBeVisible();
  await expect(page.getByText("Bounded AI demo", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Compare trade-offs"}).click();
  await expect(page.getByText(/Bounded AI demo · deterministic · deterministic_fallback/)).toBeVisible();
  await page.getByRole("button", {name: "Engineer", exact: true}).click();
  await expect(page.getByRole("heading", {name: /Engineering evidence packet/})).toBeVisible();
  await page.getByRole("button", {name: "Propose diagnostic"}).click();
  await expect(page.getByText(/case state proposed/i)).toBeVisible();
  await page.getByRole("button", {name: "Approve as yield lead"}).click();
  await expect(page.getByText(/case state approved/i)).toBeVisible();

  await page.getByRole("button", {name: /System Health/i}).click();
  await expect(page).toHaveURL(/\/SystemHealth$/);
  await expect(page.getByText("373", {exact: true}).first()).toBeVisible();
  await expect(page.getByRole("heading", {name: "Portfolio release 0.6.0"})).toBeVisible();
  await expect(page.getByText(/Container integration (verified|degraded|unverified)/)).toBeVisible();
  await expect(page.getByText(/Docker daemon unavailable in current audit/)).toHaveCount(0);

  const healthList = page.locator(".health-stat-list");
  const healthBox = await healthList.boundingBox();
  const firstHealthRow = await healthList.locator(":scope > div").first().boundingBox();
  expect(healthBox).not.toBeNull();
  expect(firstHealthRow).not.toBeNull();
  expect((firstHealthRow?.x ?? 0) - (healthBox?.x ?? 0)).toBeGreaterThanOrEqual(12);

  await page.reload();
  await expect(page).toHaveURL(/\/SystemHealth$/);
  await expect(page.getByRole("heading", {name: "Deterministic pipeline state"})).toBeVisible();
});

test("mobile decision cockpit keeps candidate, provenance and read-only identity visible", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  const ribbon = page.getByLabel("Release and provenance status");
  await expect(ribbon).toBeVisible();
  await expect(ribbon).toContainText("candidate");
  await expect(ribbon).toContainText("base 0.6.0");
  await expect(ribbon).toContainText("human authority");
  await expect(ribbon).toContainText("no equipment control");
  await expect(page.getByLabel("Section 1, Decide")).toContainText("Ⅰ. Decide");
  await expect(page.getByLabel("Section 2, Investigate")).toContainText("Ⅱ. Investigate");
  await expect(page.getByLabel("Section 3, Trust")).toContainText("Ⅲ. Trust");
  const workspaceContext = page.getByLabel("Current workspace context");
  await expect(workspaceContext).toBeVisible();
  await expect(workspaceContext).toContainText("Decision Cockpit");
  await expect(workspaceContext).toContainText(/LOT-\d{5}/);
  await expect(page.getByRole("button", {name: /Decision & Approval/i})).toBeVisible();
});

test("1024 and reduced-motion modes preserve decision authority, keyboard access and layout", async ({page}) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });

  await page.setViewportSize({width: 1024, height: 900});
  await page.goto("/DecisionCockpit");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  await ensureDesktopPanesPinned(page);
  await expect(page.getByLabel("Evidence authority separation")).toContainText("HUMAN DECISION");
  await expect(page.locator(".cockpit-trust").getByText("NO EQUIPMENT CONTROL", {exact: true})).toBeVisible();
  await expect(page.getByLabel("Section 1, Decide")).toContainText("Ⅰ. Decide");
  await expect(page.getByLabel("Section 2, Investigate")).toContainText("Ⅱ. Investigate");
  await expect(page.getByLabel("Section 3, Trust")).toContainText("Ⅲ. Trust");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)).toBe(false);

  const graphNav = page.getByRole("button", {name: /Evidence Graph/i});
  await graphNav.focus();
  await expect(graphNav).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/EvidenceGraph$/);
  await expect(graphNav).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Spatial die coordinates unavailable in current API", {exact: true})).toBeVisible();
  await expect(page.getByText("Accessible relationship fallback", {exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)).toBe(false);

  await page.emulateMedia({reducedMotion: "reduce"});
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/DecisionCockpit");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  const motionAudit = await page.evaluate(() => {
    const nav = document.querySelector(".nav-item");
    const style = nav ? getComputedStyle(nav) : null;
    return {
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      transitionDuration: style?.transitionDuration ?? "missing",
      animationName: style?.animationName ?? "missing",
    };
  });
  expect(motionAudit.overflow).toBe(false);
  expect(["0s", "missing"]).toContain(motionAudit.transitionDuration);
  expect(["none", "missing"]).toContain(motionAudit.animationName);
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("Semiconductor Forensics design grammar stays consistent across routes", async ({page}) => {
  test.setTimeout(120_000);
  const routes = [
    {path: "/DecisionCockpit", ready: ".decision-cockpit"},
    {path: "/DecisionApproval", ready: ".decision-header"},
    {path: "/ShiftHandoff", ready: ".shift-handoff"},
    {path: "/CaseInvestigation", ready: ".case-hero"},
    {path: "/EvidenceGraph", ready: ".signal-console-hero"},
    {path: "/AnalysisWorkbench", ready: ".analysis-workbench"},
    {path: "/CaseComparison", ready: ".case-comparison-workbench"},
    {path: "/OperationsQueue", ready: ".overview-visual-grid"},
    {path: "/ModelEvidence", ready: ".version-grid"},
    {path: "/SystemHealth", ready: ".release-identity-panel"},
  ];

  for (const route of routes) {
    await page.setViewportSize({width: 1440, height: 1000});
    await page.goto(route.path);
    await expect(page.locator(".app-shell")).toBeVisible();
    await ensureDesktopPanesPinned(page);
    await expect(page.locator(route.ready)).toBeVisible();
    const workspaceContext = page.getByLabel("Current workspace context");
    await expect(workspaceContext).toBeVisible();
    await expect(workspaceContext).toContainText("Decision Lab");
    const desktopAudit = await page.evaluate(() => {
      const visible = (element: Element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      };
      const textSizes = Array.from(document.querySelectorAll("main *"))
        .filter((element) => visible(element) && element.children.length === 0 && (element.textContent?.trim().length ?? 0) > 0)
        .map((element) => Number.parseFloat(getComputedStyle(element).fontSize))
        .filter(Number.isFinite);
      const undersized = Array.from(document.querySelectorAll("main *"))
        .filter((element) => visible(element) && element.children.length === 0 && (element.textContent?.trim().length ?? 0) > 0)
        .map((element) => ({
          tag: element.tagName.toLowerCase(),
          className: element.className,
          text: element.textContent?.trim().slice(0, 40),
          size: Number.parseFloat(getComputedStyle(element).fontSize),
        }))
        .filter((item) => Number.isFinite(item.size) && item.size < 10)
        .slice(0, 12);
      const panelHeaders = Array.from(document.querySelectorAll(".panel > header")).filter(visible);
      const panelTextInsets = Array.from(document.querySelectorAll("main .panel *"))
        .filter((element) => visible(element) && element.children.length === 0 && (element.textContent?.trim().length ?? 0) > 0)
        .filter((element) => !element.closest("svg") && !["INPUT", "TEXTAREA", "OPTION"].includes(element.tagName))
        .map((element) => {
          const panel = element.closest(".panel");
          if (!panel) return null;
          const range = document.createRange();
          range.selectNodeContents(element);
          const textRect = range.getBoundingClientRect();
          const panelRect = panel.getBoundingClientRect();
          return {text: element.textContent?.trim().slice(0, 40), inset: textRect.left - panelRect.left};
        })
        .filter((item): item is {text: string | undefined; inset: number} => item !== null && Number.isFinite(item.inset));
      return {
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        headerBottom: document.querySelector(".global-header")?.getBoundingClientRect().bottom ?? 0,
        workspaceContextTop: document.querySelector(".workspace-context")?.getBoundingClientRect().top ?? 0,
        workspaceContextHeight: document.querySelector(".workspace-context")?.getBoundingClientRect().height ?? 0,
        minimumTextSize: Math.min(...textSizes, 100),
        undersized,
        headerPaddingLeft: panelHeaders.map((header) => Number.parseFloat(getComputedStyle(header).paddingLeft)),
        panelRadii: Array.from(document.querySelectorAll(".panel")).filter(visible).map((panel) => Number.parseFloat(getComputedStyle(panel).borderRadius)),
        panelTextEdgeIssues: panelTextInsets.filter((item) => item.inset < 8).slice(0, 12),
      };
    });
    expect(desktopAudit.overflow, `${route.path} has desktop page overflow`).toBe(false);
    expect(desktopAudit.workspaceContextTop, `${route.path} workspace context overlaps the global header`).toBeGreaterThanOrEqual(desktopAudit.headerBottom);
    expect(desktopAudit.workspaceContextHeight, `${route.path} lost the compact workspace context bar`).toBeGreaterThanOrEqual(32);
    expect(desktopAudit.workspaceContextHeight, `${route.path} workspace context bar became oversized`).toBeLessThanOrEqual(40);
    expect(desktopAudit.minimumTextSize, `${route.path} renders text below the 10px metadata floor: ${JSON.stringify(desktopAudit.undersized)}`).toBeGreaterThanOrEqual(10);
    expect(desktopAudit.headerPaddingLeft.every((value) => value >= 16), `${route.path} panel header inset drift`).toBe(true);
    expect(desktopAudit.panelRadii.every((value) => value >= 12), `${route.path} panel radius drift`).toBe(true);
    expect(desktopAudit.panelTextEdgeIssues, `${route.path} has panel text against the left edge`).toEqual([]);

    await page.setViewportSize({width: 390, height: 844});
    await page.reload();
    await expect(page.locator(route.ready)).toBeVisible();
    const mobileAudit = await page.evaluate(() => {
      const header = document.querySelector(".global-header")?.getBoundingClientRect();
      const context = document.querySelector(".workspace-context")?.getBoundingClientRect();
      const ribbon = document.querySelector(".mobile-status-ribbon")?.getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        headerBottom: header?.bottom ?? 0,
        contextTop: context?.top ?? 0,
        contextBottom: context?.bottom ?? 0,
        ribbonTop: ribbon?.top ?? 0,
      };
    });
    expect(mobileAudit.overflow, `${route.path} has mobile page overflow`).toBe(false);
    expect(mobileAudit.contextTop, `${route.path} mobile workspace context overlaps the global header`).toBeGreaterThanOrEqual(mobileAudit.headerBottom);
    expect(mobileAudit.ribbonTop, `${route.path} mobile status ribbon overlaps the workspace context`).toBeGreaterThanOrEqual(mobileAudit.contextBottom);
  }

  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto("/SystemHealth");
  await expect(page.locator(".release-identity-panel")).toBeVisible();
  const releaseGeometry = await page.evaluate(() => {
    const panel = document.querySelector(".release-identity-panel")!.getBoundingClientRect();
    const firstRow = document.querySelector(".release-identity-list > div")!.getBoundingClientRect();
    const firstLabel = document.querySelector(".release-identity-list dt")!.getBoundingClientRect();
    return {
      firstRowInset: firstRow.left - panel.left,
      firstLabelInset: firstLabel.left - panel.left,
    };
  });
  expect(releaseGeometry.firstRowInset).toBeGreaterThanOrEqual(15);
  expect(releaseGeometry.firstLabelInset).toBeGreaterThanOrEqual(15);
});

test("desktop workbench panes preview from the edges and remain open only when pinned", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto("/DecisionCockpit");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();

  const navigation = page.getByLabel("Primary navigation");
  const navigationEdge = page.getByRole("button", {name: "Open navigation pane"});
  await expect(navigation).toBeHidden();
  await navigationEdge.hover();
  await expect(navigation).toBeVisible();
  await expect(page.getByLabel("Section 1, Decide")).toContainText("Ⅰ. Decide");
  await page.locator("#work-surface").hover({position: {x: 300, y: 100}});
  await expect(navigation).toBeHidden();

  await navigationEdge.click();
  await page.locator(".pane-pin-toolbar--dark").getByRole("button", {name: "Pin navigation pane"}).click();
  await page.locator("#work-surface").hover({position: {x: 300, y: 100}});
  await expect(navigation).toBeVisible();

  const inspectorEdge = page.getByRole("button", {name: "Open inspector pane"});
  await inspectorEdge.hover();
  await expect(page.getByLabel("Evidence inspector")).toBeVisible();
  await page.locator(".evidence-inspector-slot .pane-pin-toolbar").getByRole("button", {name: "Pin inspector pane"}).click();
  await page.locator("#work-surface").hover({position: {x: 300, y: 100}});
  await expect(page.getByLabel("Evidence inspector")).toBeVisible();
  await expect(page.getByLabel("Workbench pane controls").getByRole("button", {name: "Pin navigation pane"})).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Workbench pane controls").getByRole("button", {name: "Pin inspector pane"})).toHaveAttribute("aria-pressed", "true");
});

test("SystemHealth replay keeps the timeline above responsive selected-event details", async ({page}) => {
  await page.setViewportSize({width: 1180, height: 1000});
  await page.goto("/SystemHealth");

  const timeline = page.getByRole("list", {name: "Case replay event timeline"});
  const inspector = page.getByRole("article", {name: "Selected replay event"});
  const metadata = page.getByRole("region", {name: "Selected source event metadata"});
  const payload = page.getByRole("region", {name: "Recorded payload"});
  await expect(timeline).toBeVisible();
  await expect(inspector).toBeVisible();
  await expect(metadata).toContainText("local-event-adapter");
  const initialMetadata = await metadata.textContent();
  const initialPayload = await payload.textContent();

  const wideGeometry = await page.evaluate(() => {
    const timelineRect = document.querySelector("[aria-label='Case replay event timeline']")!.getBoundingClientRect();
    const inspectorRect = document.querySelector("[aria-label='Selected replay event']")!.getBoundingClientRect();
    const metadataRect = document.querySelector("[aria-label='Selected source event metadata']")!.getBoundingClientRect();
    const payloadRect = document.querySelector("[aria-label='Recorded payload']")!.getBoundingClientRect();
    return {timelineRect, inspectorRect, metadataRect, payloadRect};
  });
  expect(wideGeometry.inspectorRect.top).toBeGreaterThanOrEqual(wideGeometry.timelineRect.bottom - 1);
  expect(wideGeometry.metadataRect.left).toBeLessThan(wideGeometry.payloadRect.left);
  expect(Math.abs(wideGeometry.metadataRect.top - wideGeometry.payloadRect.top)).toBeLessThanOrEqual(1);

  await timeline.getByRole("button").nth(1).click();
  await expect(metadata).not.toHaveText(initialMetadata ?? "");
  await expect(payload).not.toHaveText(initialPayload ?? "");

  await page.setViewportSize({width: 390, height: 844});
  const narrowGeometry = await page.evaluate(() => {
    const metadataRect = document.querySelector("[aria-label='Selected source event metadata']")!.getBoundingClientRect();
    const payloadRect = document.querySelector("[aria-label='Recorded payload']")!.getBoundingClientRect();
    return {metadataRect, payloadRect};
  });
  expect(narrowGeometry.payloadRect.top).toBeGreaterThanOrEqual(narrowGeometry.metadataRect.bottom - 1);
});

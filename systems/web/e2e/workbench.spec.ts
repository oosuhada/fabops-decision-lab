import {expect, test} from "@playwright/test";

test("decision cockpit connects priority, evidence, grounded brief and governed approval", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  await expect(page).toHaveURL(/\/DecisionCockpit$/);
  const header = page.locator(".global-header");
  await expect(header.getByText("0.7 CANDIDATE", {exact: true})).toBeVisible();
  await expect(header.getByText("READ-ONLY PREVIEW", {exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Compare the available stances before acting"})).toBeVisible();
  await expect(page.getByText("Current recommendation").first()).toBeVisible();
  await page.getByRole("button", {name: "Investigate evidence"}).click();
  await expect(page.getByRole("heading", {name: /Is .* the best explanation\?/i})).toBeVisible();
  await expect(page.getByRole("heading", {name: /What supports — and weakens — the hypothesis\?/i})).toBeVisible();

  await page.getByRole("button", {name: /Evidence Graph/i}).click();
  await expect(page).toHaveURL(/\/EvidenceGraph$/);
  await expect(page.getByRole("heading", {name: /lineage/i})).toBeVisible();
  await page.getByRole("button", {name: /ETCH/i}).first().click();
  await expect(page.getByRole("img", {name: /ETCH normalized measurement series/i})).toBeVisible();

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
  await expect(ribbon).toContainText("0.7 candidate");
  await expect(ribbon).toContainText("synthetic");
  await expect(ribbon).toContainText("read-only");
  await expect(ribbon).toContainText("base 0.6.0");
  await expect(page.getByRole("button", {name: /Decision & Approval/i})).toBeVisible();
});

test("Foundry Glass design grammar stays consistent across routes", async ({page}) => {
  const routes = [
    {path: "/DecisionCockpit", ready: ".decision-cockpit"},
    {path: "/DecisionApproval", ready: ".decision-header"},
    {path: "/CaseInvestigation", ready: ".case-hero"},
    {path: "/EvidenceGraph", ready: ".signal-console-hero"},
    {path: "/OperationsQueue", ready: ".overview-visual-grid"},
    {path: "/ModelEvidence", ready: ".version-grid"},
    {path: "/SystemHealth", ready: ".release-identity-panel"},
  ];

  for (const route of routes) {
    await page.setViewportSize({width: 1440, height: 1000});
    await page.goto(route.path);
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator(route.ready)).toBeVisible();
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
      return {
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        minimumTextSize: Math.min(...textSizes, 100),
        undersized,
        headerPaddingLeft: panelHeaders.map((header) => Number.parseFloat(getComputedStyle(header).paddingLeft)),
        panelRadii: Array.from(document.querySelectorAll(".panel")).filter(visible).map((panel) => Number.parseFloat(getComputedStyle(panel).borderRadius)),
      };
    });
    expect(desktopAudit.overflow, `${route.path} has desktop page overflow`).toBe(false);
    expect(desktopAudit.minimumTextSize, `${route.path} renders text below the 10px metadata floor: ${JSON.stringify(desktopAudit.undersized)}`).toBeGreaterThanOrEqual(10);
    expect(desktopAudit.headerPaddingLeft.every((value) => value >= 16), `${route.path} panel header inset drift`).toBe(true);
    expect(desktopAudit.panelRadii.every((value) => value >= 12), `${route.path} panel radius drift`).toBe(true);

    await page.setViewportSize({width: 390, height: 844});
    await page.reload();
    await expect(page.locator(route.ready)).toBeVisible();
    const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    expect(mobileOverflow, `${route.path} has mobile page overflow`).toBe(false);
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


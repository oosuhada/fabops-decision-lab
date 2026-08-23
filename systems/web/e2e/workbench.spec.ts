import {expect, test} from "@playwright/test";

test("decision cockpit connects priority, evidence, grounded brief and governed approval", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  const header = page.locator(".global-header");
  await expect(header.getByText("0.7 CANDIDATE", {exact: true})).toBeVisible();
  await expect(header.getByText("READ-ONLY PREVIEW", {exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Compare the available stances before acting"})).toBeVisible();
  await expect(page.getByText("Current recommendation").first()).toBeVisible();
  await page.getByRole("button", {name: "Investigate evidence"}).click();
  await expect(page.getByRole("heading", {name: /Is .* the best explanation\?/i})).toBeVisible();
  await expect(page.getByRole("heading", {name: /What supports — and weakens — the hypothesis\?/i})).toBeVisible();

  await page.getByRole("button", {name: /Evidence Graph/i}).click();
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
  await page.getByRole("button", {name: "Engineer"}).click();
  await expect(page.getByRole("heading", {name: /Engineering evidence packet/})).toBeVisible();
  await page.getByRole("button", {name: "Propose diagnostic"}).click();
  await expect(page.getByText(/case state proposed/i)).toBeVisible();
  await page.getByRole("button", {name: "Approve as yield lead"}).click();
  await expect(page.getByText(/case state approved/i)).toBeVisible();

  await page.getByRole("button", {name: /System Health/i}).click();
  await expect(page.getByText("373", {exact: true}).first()).toBeVisible();
  await expect(page.getByRole("heading", {name: "Portfolio release 0.6.0"})).toBeVisible();
  await expect(page.getByText(/Container integration (verified|degraded|unverified)/)).toBeVisible();
  await expect(page.getByText(/Docker daemon unavailable in current audit/)).toHaveCount(0);
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
  await expect(ribbon).toContainText("0.6.0");
  await expect(page.getByRole("button", {name: /Decision & Approval/i})).toBeVisible();
});


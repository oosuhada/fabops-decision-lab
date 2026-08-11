import {expect, test} from "@playwright/test";

test("API-backed engineering decision workbench stays consistent across overview, evidence and approval", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Yield excursion triage queue"})).toBeVisible();
  await expect(page.getByText("373", {exact: true}).first()).toBeVisible();
  const firstCase = page.getByRole("button", {name: /^CASE-/}).first();
  await firstCase.click();
  await expect(page.getByText("Advisory · LLM off", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: /Evidence Graph/i}).click();
  await expect(page.getByRole("heading", {name: /lineage/i})).toBeVisible();
  await page.getByRole("button", {name: /ETCH/i}).first().click();
  await expect(page.getByRole("img", {name: /ETCH normalized measurement series/i})).toBeVisible();

  await page.getByRole("button", {name: /Decision & Approval/i}).click();
  await expect(page.getByText(/PROPOSAL ONLY · NO TOOL CONTROL/)).toBeVisible();
  await expect(page.getByRole("button", {name: /execute equipment/i})).toHaveCount(0);
  await page.getByRole("button", {name: "Propose diagnostic"}).click();
  await expect(page.getByRole("heading", {name: /Case state: proposed/i})).toBeVisible();
  await page.getByRole("button", {name: "Approve as yield lead"}).click();
  await expect(page.getByRole("heading", {name: /Case state: approved/i})).toBeVisible();

  await page.getByRole("button", {name: /Replay & Operations/i}).click();
  await expect(page.getByText("373", {exact: true}).first()).toBeVisible();
  await expect(page.getByText(/Container integration (verified|degraded|unverified)/)).toBeVisible();
  await expect(page.getByText(/Docker daemon unavailable in current audit/)).toHaveCount(0);
});


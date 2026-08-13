import {expect, test} from "@playwright/test";

test("decision cockpit connects priority, evidence, grounded brief and governed approval", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "What needs an engineering decision now?"})).toBeVisible();
  await expect(page.getByText("RELEASE 0.6.0")).toBeVisible();
  await expect(page.getByText("Decision queue", {exact: true}).first()).toBeVisible();
  await expect(page.getByText(/Recommended stance:/).first()).toBeVisible();
  await page.getByRole("button", {name: "Inspect evidence"}).click();
  await expect(page.getByText("Advisory · LLM off", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: /Evidence Graph/i}).click();
  await expect(page.getByRole("heading", {name: /lineage/i})).toBeVisible();
  await page.getByRole("button", {name: /ETCH/i}).first().click();
  await expect(page.getByRole("img", {name: /ETCH normalized measurement series/i})).toBeVisible();

  await page.getByRole("button", {name: /Decision & Approval/i}).click();
  await expect(page.getByText(/PROPOSAL ONLY · NO TOOL CONTROL/)).toBeVisible();
  await expect(page.getByRole("button", {name: /execute equipment/i})).toHaveCount(0);
  await expect(page.getByText("Grounded decision brief", {exact: true})).toBeVisible();
  await expect(page.getByText("deterministic_fallback", {exact: true})).toBeVisible();
  await expect(page.getByText("deterministic", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Engineer"}).click();
  await expect(page.getByRole("heading", {name: /Engineering evidence packet/})).toBeVisible();
  await page.getByRole("button", {name: "Propose diagnostic"}).click();
  await expect(page.getByRole("heading", {name: /Case state: proposed/i})).toBeVisible();
  await page.getByRole("button", {name: "Approve as yield lead"}).click();
  await expect(page.getByRole("heading", {name: /Case state: approved/i})).toBeVisible();

  await page.getByRole("button", {name: /Replay & Operations/i}).click();
  await expect(page.getByText("373", {exact: true}).first()).toBeVisible();
  await expect(page.getByRole("heading", {name: "Portfolio release 0.6.0"})).toBeVisible();
  await expect(page.getByText(/Container integration (verified|degraded|unverified)/)).toBeVisible();
  await expect(page.getByText(/Docker daemon unavailable in current audit/)).toHaveCount(0);
});


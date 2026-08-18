import {expect, test} from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const captureEnabled = process.env.FABOPS_CAPTURE_VISUAL_EVIDENCE === "1";
const outputDir = fileURLToPath(new URL("../../../docs/assets/semiconductor-forensics-v2/", import.meta.url));

test("capture Semiconductor Forensics V2 browser evidence", async ({page}) => {
  test.skip(!captureEnabled, "Visual evidence capture is opt-in so normal verification does not overwrite versioned screenshots.");
  fs.mkdirSync(outputDir, {recursive: true});

  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });

  for (const [width, height, filename] of [
    [1440, 1000, "decision-cockpit-1440.png"],
    [1024, 900, "decision-cockpit-1024.png"],
    [390, 844, "decision-cockpit-390.png"],
  ] as const) {
    await page.setViewportSize({width, height});
    await page.goto("/DecisionCockpit");
    await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)).toBe(false);
    await page.screenshot({path: path.join(outputDir, filename), fullPage: true});
  }

  for (const [width, height, filename] of [
    [1440, 1000, "evidence-graph-1440.png"],
    [1024, 900, "evidence-graph-1024.png"],
  ] as const) {
    await page.setViewportSize({width, height});
    await page.goto("/EvidenceGraph");
    await expect(page.getByText("Accessible relationship fallback", {exact: true})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)).toBe(false);
    await page.screenshot({path: path.join(outputDir, filename), fullPage: true});
  }

  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto("/EvidenceGraph");
  const measurement = page.getByRole("treeitem", {name: /Measurement /i}).first();
  await measurement.click();
  await expect(page.getByLabel("Evidence inspector")).toContainText("Observed fact");
  await page.screenshot({path: path.join(outputDir, "evidence-inspector-1440.png"), fullPage: true});

  await page.emulateMedia({reducedMotion: "reduce"});
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/DecisionCockpit");
  await expect(page.getByRole("heading", {name: "What needs a decision now?"})).toBeVisible();
  await page.screenshot({path: path.join(outputDir, "decision-cockpit-390-reduced-motion.png"), fullPage: true});

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

import {expect, test} from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const outputDir = path.resolve(process.cwd(), "../../evidence/ui-review/0.6.0");
const releaseHash = "ab8b20a696b9b1996495f23a3e413cc33a67b6861efa184c64742e0f310c6326";

const screens = [
  ["Operations Overview", "operations-overview"],
  ["Excursion Case", "excursion-case"],
  ["Evidence Graph", "evidence-graph"],
  ["Decision & Approval", "decision-approval"],
  ["Evaluation Lab", "evaluation-lab"],
  ["Replay & Operations", "replay-operations"],
] as const;

test("capture immutable 0.6.0 public read-only review baseline", async ({page}) => {
  fs.mkdirSync(outputDir, {recursive: true});

  await page.goto("/");
  await expect(page.getByText("FabOps Decision Lab", {exact: true})).toBeVisible();
  await expect(page.getByText("RELEASE 0.6.0", {exact: true})).toBeVisible();
  await expect(page.getByText("NO EQUIPMENT CONTROL", {exact: true})).toBeVisible();
  await expect(page.getByText("Source: synthetic events · result: inferred", {exact: true})).toBeVisible();

  const apiAudit = await page.evaluate(async (expectedHash) => {
    const getJson = async (url: string) => {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`${url} returned ${response.status}`);
      return response.json();
    };
    const release = await getJson("/api/release");
    const overview = await getJson("/api/overview");
    const evaluation = await getJson("/api/evaluation");
    const replay = await getJson("/api/replay");
    const caseId = overview.cases[0].case_id as string;
    const detail = await getJson(`/api/cases/${caseId}`);
    const advisory = await getJson(`/api/cases/${caseId}/advisory`);
    const serialized = JSON.stringify({release, overview, evaluation, replay, detail, advisory});
    const blocked = await fetch("/api/cases/NONEXISTENT/actions/approve", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-FabOps-Role": "yield_lead"},
      body: JSON.stringify({reason: "read-only preview verification"}),
    });
    return {
      releaseVersion: release.release_version,
      releaseHash: release.release_hash,
      expectedHash,
      groundTruthPresent: serialized.includes("ground_truth"),
      mutationStatus: blocked.status,
      caseId,
    };
  }, releaseHash);

  expect(apiAudit.releaseVersion).toBe("0.6.0");
  expect(apiAudit.releaseHash).toBe(releaseHash);
  expect(apiAudit.releaseHash).toBe(apiAudit.expectedHash);
  expect(apiAudit.groundTruthPresent).toBe(false);
  expect(apiAudit.mutationStatus).toBe(405);

  for (const [label, slug] of screens) {
    const navButton = page.getByRole("button", {name: new RegExp(label.replace(/[&]/g, "\\&"), "i")});
    await navButton.click();
    await expect(navButton).toHaveAttribute("aria-current", "page");
    await page.screenshot({path: path.join(outputDir, `desktop-1440x1000-${slug}.png`)});
  }

  await page.setViewportSize({width: 1280, height: 800});
  await page.getByRole("button", {name: /Operations Overview/i}).click();
  await page.screenshot({path: path.join(outputDir, "responsive-1280x800-operations-overview.png")});

  await page.setViewportSize({width: 390, height: 844});
  await page.reload();
  await expect(page.getByRole("heading", {name: "Yield excursion triage queue"})).toBeVisible();
  await page.screenshot({path: path.join(outputDir, "responsive-390x844-operations-overview.png")});
});

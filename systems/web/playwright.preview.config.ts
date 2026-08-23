import {defineConfig} from "@playwright/test";

const baseURL = process.env.FABOPS_PREVIEW_URL ?? "https://fabops-preview.oosu.dev";
const resolverIp = process.env.FABOPS_PREVIEW_IP;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "ui-review.spec.ts",
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL,
    viewport: {width: 1440, height: 1000},
    launchOptions: resolverIp
      ? {args: [`--host-resolver-rules=MAP fabops-preview.oosu.dev ${resolverIp}`]}
      : undefined,
  },
});

import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.FABOPS_E2E_API_PORT ?? "8000";
const webPort = process.env.FABOPS_E2E_WEB_PORT ?? "5173";
const apiBaseURL = `http://127.0.0.1:${apiPort}`;
const webBaseURL = `http://127.0.0.1:${webPort}`;
const externalBaseURL = process.env.FABOPS_E2E_EXTERNAL_URL?.replace(/\/$/, "");
const effectiveBaseURL = externalBaseURL ?? webBaseURL;

export default defineConfig({
  testDir: "./e2e",
  testIgnore: "ui-review.spec.ts",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: effectiveBaseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {...devices["Desktop Chrome"]},
    },
  ],
  webServer: externalBaseURL ? undefined : [
    {
      command: `/opt/homebrew/bin/uv run uvicorn systems.api.app:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../..",
      url: `${apiBaseURL}/health`,
      env: {
        ...process.env,
        FABOPS_CORS_ORIGINS: webBaseURL,
        FABOPS_PUBLIC_NARRATION_CACHE_ONLY: "true",
        FABOPS_PUBLIC_AI_DEMO_ENABLED: "true",
        FABOPS_DEMO_SESSION_SECRET: "playwright-demo-session-secret-not-for-production",
        FABOPS_DEMO_MAX_GENERATIONS_PER_SESSION: "5",
        FABOPS_DEPLOYMENT_KIND: "candidate",
        FABOPS_DEPLOYMENT_CHANNEL: "public-preview",
        FABOPS_CANDIDATE_LABEL: "0.6.0-v0.7-candidate",
        FABOPS_CANDIDATE_GIT_SHA: "e2e-candidate-sha",
        FABOPS_DEPLOYMENT_HASH: "candidate-e2e-candidate-sha",
      },
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `VITE_API_URL=${apiBaseURL} npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      cwd: ".",
      url: webBaseURL,
      reuseExistingServer: false,
      timeout: 30_000,
    }
  ]
});


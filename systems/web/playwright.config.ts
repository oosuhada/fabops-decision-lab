import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.FABOPS_E2E_API_PORT ?? "8000";
const webPort = process.env.FABOPS_E2E_WEB_PORT ?? "5173";
const apiBaseURL = `http://127.0.0.1:${apiPort}`;
const webBaseURL = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "./e2e",
  testIgnore: "ui-review.spec.ts",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: webBaseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {...devices["Desktop Chrome"]},
    },
  ],
  webServer: [
    {
      command: `/opt/homebrew/bin/uv run uvicorn systems.api.app:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../..",
      url: `${apiBaseURL}/health`,
      env: {
        ...process.env,
        FABOPS_PUBLIC_NARRATION_CACHE_ONLY: "true",
        FABOPS_PUBLIC_AI_DEMO_ENABLED: "true",
        FABOPS_DEMO_SESSION_SECRET: "playwright-demo-session-secret-not-for-production",
        FABOPS_DEMO_MAX_GENERATIONS_PER_SESSION: "5",
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


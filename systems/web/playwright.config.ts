import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: "ui-review.spec.ts",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:5173",
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
      command: "/opt/homebrew/bin/uv run uvicorn systems.api.app:app --host 127.0.0.1 --port 8000",
      cwd: "../..",
      url: "http://127.0.0.1:8000/health",
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
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      cwd: ".",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 30_000,
    }
  ]
});


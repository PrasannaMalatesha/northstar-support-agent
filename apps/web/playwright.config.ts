import path from "node:path";
import { defineConfig } from "@playwright/test";

const webRoot = process.cwd();
const repoRoot = path.resolve(webRoot, "../..");

const databaseUrl =
  process.env.DATABASE_URL ?? "postgresql://northstar:northstar@localhost:5433/northstar";

const env = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
);

export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:3100" },
  webServer: [
    {
      command: "uv run uvicorn northstar_api.main:app --host 127.0.0.1 --port 8010",
      cwd: repoRoot,
      url: "http://127.0.0.1:8010/health",
      timeout: 120_000,
      reuseExistingServer: false,
      // Live chat is on here, so the suite covers it and every older screen with it on (issue #138).
      // A quiet specialist is flagged to the lead after 3 seconds, not 2 minutes, so the lead's alert shows (issue #144).
      // Staff API tokens last 90 seconds, not 15 minutes, so the console renews them during the suite.
      env: {
        ...env,
        DATABASE_URL: databaseUrl,
        LIVE_CHAT_ENABLED: "true",
        QUIET_SPECIALIST_MINUTES: "0.05",
        ACCESS_TOKEN_MINUTES: "1.5",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
      cwd: webRoot,
      url: "http://127.0.0.1:3100/login",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...env,
        AUTH_SECRET: "playwright-auth-secret-at-least-32-characters",
        AUTH_TRUST_HOST: "true",
        FASTAPI_URL: "http://127.0.0.1:8010",
      },
    },
  ],
});

// Records the console part of the submission walkthrough as a video.
// Not part of CI: the spec lives outside tests/. Run it against a fresh database.
import path from "node:path";
import { defineConfig } from "@playwright/test";

const webRoot = process.cwd();
const repoRoot = path.resolve(webRoot, "../..");

const databaseUrl =
  process.env.WALKTHROUGH_DATABASE_URL ??
  "postgresql://northstar:northstar@localhost:5433/northstar_walkthrough";

const env = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
);

export default defineConfig({
  testDir: "walkthrough",
  outputDir: "walkthrough-results",
  timeout: 300_000,
  use: {
    baseURL: "http://127.0.0.1:3100",
    viewport: { width: 1280, height: 800 },
    video: { mode: "on", size: { width: 1280, height: 800 } },
    launchOptions: { slowMo: 150 },
  },
  webServer: [
    {
      command: "uv run uvicorn northstar_api.main:app --host 127.0.0.1 --port 8010",
      cwd: repoRoot,
      url: "http://127.0.0.1:8010/health",
      timeout: 120_000,
      reuseExistingServer: false,
      env: { ...env, DATABASE_URL: databaseUrl },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
      cwd: webRoot,
      url: "http://127.0.0.1:3100/login",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...env,
        AUTH_SECRET: "walkthrough-auth-secret-at-least-32-characters",
        AUTH_TRUST_HOST: "true",
        FASTAPI_URL: "http://127.0.0.1:8010",
      },
    },
  ],
});

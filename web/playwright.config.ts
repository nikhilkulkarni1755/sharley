import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const DEPLOY_URL = process.env.DEPLOY_URL;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  projects: [
    {
      name: "mocked",
      testIgnore: "deploy.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: `http://localhost:${PORT}` },
    },
    {
      name: "deployed",
      testMatch: "deploy.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: DEPLOY_URL },
    },
  ],
  // The static export is built against its own origin so page.route can serve the API without CORS.
  webServer: DEPLOY_URL
    ? undefined
    : {
        command: `NEXT_PUBLIC_API_URL=http://localhost:${PORT} npm run build && npx serve out -l ${PORT}`,
        url: `http://localhost:${PORT}`,
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
      },
});

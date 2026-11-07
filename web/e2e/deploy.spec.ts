import { expect, test } from "@playwright/test";

const DEPLOY_URL = process.env.DEPLOY_URL;
const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test.skip(!DEPLOY_URL, "DEPLOY_URL is not set");

test("the deployed site loads with no console errors and the security headers", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));

  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("tab", { name: "Intake" })).toBeVisible();

  const headers = response!.headers();
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBeTruthy();
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["content-security-policy"]).toContain("default-src 'self'");

  expect(errors.filter((e) => !/health|demo|Failed to load resource/i.test(e))).toEqual([]);
});

test("the Eval tab renders from the replay fixture", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Eval" }).click();
  await expect(page.getByTestId("version-card").first()).toBeVisible();
  await expect(page.locator('[data-decision="adopted"]').first()).toBeVisible();
  await expect(page.getByTestId("curve-line")).toBeVisible();
});

test("the API answers /api/health", async ({ request }) => {
  const res = await request.get(`${API_URL}/api/health`);
  expect(res.ok()).toBe(true);
  expect(await res.json()).toHaveProperty("providers");
});

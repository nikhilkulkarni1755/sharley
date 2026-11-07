import { expect, test, type Page } from "@playwright/test";
import { alertOf, mockApi, repoSamples, sseBody } from "./mock";

const surface = { type: "surface", stack: "fastapi", files: 12, routes: 5, env_vars: 2 };
const finding = {
  type: "finding",
  id: "t1",
  name: "test_notes_are_private",
  family: "security",
  requirement_ids: ["R8"],
  requirement_text: "Notes are private to their owner",
  kind: "assert",
  message: "x".repeat(400),
};
const auditStream = (report: object) =>
  sseBody([
    { type: "stage", stage: "cloning", detail: "git clone" },
    { type: "stage", stage: "running_tests", detail: "running 10 tests" },
    surface,
    finding,
    report,
  ]);

const open = async (page: Page, url = "https://github.com/acme/notes") => {
  await page.goto("/");
  await page.getByRole("tab", { name: "GitHub repo" }).click();
  await page.getByLabel("Repo URL").fill(url);
};
const verify = (page: Page) => page.getByRole("button", { name: "Verify repo" }).click();

test.beforeEach(({ page }) => mockApi(page));

test("is the second tab and a sample quick-pick fills the URL", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("tab").nth(1)).toHaveText("GitHub repo");
  await page.getByRole("tab", { name: "GitHub repo" }).click();
  await expect(page.getByText("PRE-BUILT", { exact: true })).toBeVisible();
  await expect(page.getByText("Public GitHub repos only.")).toBeVisible();
  await page.getByRole("button", { name: /Shop API/ }).click();
  await expect(page.getByLabel("Repo URL")).toHaveValue(repoSamples[1].url);
  await expect(page.getByText(repoSamples[1].pitch)).toBeVisible();
});

test("an invalid URL is blocked client-side", async ({ page }) => {
  let posted = false;
  await page.route("**/api/repos", (r) => {
    posted = true;
    return r.abort();
  });
  await open(page, "https://gitlab.com/acme/notes");
  await verify(page);
  await expect(alertOf(page)).toContainText("public repo URL");
  expect(posted).toBe(false);
});

test("sealed mode posts the url and branch and streams to a verdict", async ({ page }) => {
  await open(page);
  await page.getByLabel("Branch (optional)").fill("dev");
  const request = page.waitForRequest("**/api/repos");
  await verify(page);
  expect((await request).postDataJSON()).toEqual({ url: "https://github.com/acme/notes", branch: "dev" });
  const banner = page.getByRole("region", { name: "Verdict" });
  await expect(banner).toContainText("Wrong Answer on sealed test 37 of 58");
  await expect(banner).toContainText("Hidden sealed tests: 55/58 passed");
  await expect(page.getByText("LIVE", { exact: true })).toBeVisible();
});

test("audit mode shows stages, surface tiles, finding cards and the report", async ({ page }) => {
  await page.unroute("**/api/repos");
  await page.route("**/api/repos", (r) => r.fulfill({ status: 202, json: { run_id: "run1", mode: "audit" } }));
  await page.unroute("**/api/runs/*/events");
  await page.route("**/api/runs/*/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: auditStream({ type: "report", total: 10, passed: 7, failed: 3, boot_ok: true, build_output: "" }) }),
  );
  await open(page);
  await verify(page);
  await expect(page.getByRole("heading", { name: "7 of 10 generated tests passed", exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Progress" }).locator("li")).toHaveCount(4);
  const tiles = page.getByRole("list", { name: "Repo surface" });
  await expect(tiles).toContainText("12");
  await expect(tiles).toContainText("fastapi");
  const card = page.locator(".finding");
  await expect(card).toContainText("test_notes_are_private");
  await expect(card).toContainText("R8");
  await expect(card).toContainText("Notes are private to their owner");
  await card.locator("summary").click();
  await expect(card.locator("code")).toHaveText(`${"x".repeat(300)}…`);
});

test("a repo that cannot boot explains the sandbox", async ({ page }) => {
  await page.unroute("**/api/runs/*/events");
  await page.route("**/api/runs/*/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: sseBody([{ type: "report", total: 0, passed: 0, failed: 0, boot_ok: false, build_output: "ModuleNotFoundError: torch" }]) }),
  );
  await open(page);
  await verify(page);
  await expect(page.getByText("Could not start this repo with the standard runner")).toBeVisible();
  await expect(page.getByText("no network and a fixed set of Python libraries")).toBeVisible();
  await page.getByText("Build output").click();
  await expect(page.getByText("ModuleNotFoundError: torch")).toBeVisible();
});

for (const [status, detail, message] of [
  [403, "admin key required", "Live repo audit is disabled on this public link. Try a sample repo."],
  [422, "branch not found", "branch not found"],
  [429, "slow down", "busy or rate limited"],
] as const) {
  test(`${status} shows a friendly message`, async ({ page }) => {
    await page.unroute("**/api/repos");
    await page.route("**/api/repos", (r) => r.fulfill({ status, json: { detail } }));
    await open(page);
    await verify(page);
    await expect(alertOf(page)).toContainText(message);
  });
}

test("a stream error event is shown", async ({ page }) => {
  await page.unroute("**/api/runs/*/events");
  await page.route("**/api/runs/*/events", (r) => r.fulfill({ contentType: "text/event-stream", body: sseBody([{ type: "error", detail: "clone failed" }]) }));
  await open(page);
  await verify(page);
  await expect(alertOf(page)).toContainText("clone failed");
});

test("no horizontal scroll at 390px on the repo tab", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.unroute("**/api/runs/*/events");
  await page.route("**/api/runs/*/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: auditStream({ type: "report", total: 10, passed: 7, failed: 3, boot_ok: true, build_output: "" }) }),
  );
  await open(page);
  await verify(page);
  await expect(page.getByRole("region", { name: "Report" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/repo-mobile.png", fullPage: true });
});

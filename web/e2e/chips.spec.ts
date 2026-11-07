import { expect, test } from "@playwright/test";
import { demo, mockApi } from "./mock";

test.beforeEach(({ page }) => mockApi(page));

test("the header describes the product and the tabs sit above the fold at 1280x720", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sharley" })).toBeVisible();
  await expect(page.getByText("Independent Security and QA verifier for AI Code!", { exact: true })).toBeVisible();
  await expect(page.getByText("Give it a spec, a photo of a whiteboard, or a GitHub repo.")).toBeVisible();
  const box = await page.getByRole("tab", { name: "Eval" }).boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(720);
  await page.screenshot({ path: "test-results/header-desktop.png" });
});

test("the header fits 390px without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/header-mobile.png" });
});

test("Playground is PRE-BUILT, then LIVE after a run, with both count lines and the explanatory note", async ({ page }) => {
  await page.goto("/");
  const panel = page.getByRole("tabpanel", { name: "Playground" });
  await expect(panel.getByText("PRE-BUILT", { exact: true })).toBeVisible();
  await expect(panel.getByText("no model is called")).toBeVisible();
  await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Run sealed tests" }).click();
  await expect(panel.getByText("LIVE", { exact: true })).toBeVisible();
  const banner = page.getByRole("region", { name: "Verdict" });
  await expect(banner).toContainText("Visible examples: 12/12 passed");
  await expect(banner).toContainText("Hidden sealed tests: 55/58 passed");
  await expect(banner).toContainText("Passes everything you can see but fails hidden tests");
});

test("Eval and Judge replay are RECORDED with the fixture's note and source", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Eval" }).click();
  const evalPanel = page.getByRole("tabpanel", { name: "Eval" });
  await expect(evalPanel.getByText("RECORDED", { exact: true })).toBeVisible();
  await expect(evalPanel.getByText(`Generated ${demo.meta.generated_at}`)).toBeVisible();
  await expect(evalPanel.getByText("Real Docker runs of the notes reference app; the test writer was a scripted stand-in, not a model.")).toBeVisible();
  await evalPanel.getByText("What's recorded?").click();
  await expect(evalPanel.getByText(demo.meta.note, { exact: true })).toBeVisible();
  await expect(evalPanel.getByText(demo.meta.source, { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Judge" }).click();
  const judge = page.getByRole("tabpanel", { name: "Judge" });
  await expect(judge.getByText("RECORDED", { exact: true })).toBeVisible();
  await expect(judge.getByText("Replay = recorded")).toBeVisible();
});

test("Intake results are LIVE", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Intake" }).click();
  await page.getByLabel(/paste a spec/i).fill("Users sign up and keep private notes.");
  await page.getByRole("button", { name: "Build spec" }).click();
  await expect(page.getByRole("tabpanel", { name: "Intake" }).getByText("LIVE", { exact: true })).toBeVisible();
});

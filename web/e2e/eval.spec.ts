import { expect, test } from "@playwright/test";
import { demo, mockApi } from "./mock";

test.beforeEach(({ page }) => mockApi(page));

test("eval tab shows scores, mutants, the score curve and the version timeline", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Eval" }).click();

  const s = demo.eval.scores;
  await expect(page.getByText("Held-out mutation score")).toBeVisible();
  await expect(page.getByText(`${(s.heldout_mutation_score * 100).toFixed(1)}%`)).toBeVisible();
  await expect(page.getByText("False failure rate")).toBeVisible();
  await expect(page.getByText("Security kill rate")).toBeVisible();
  await expect(page.getByText(s.production_worthy.toFixed(3), { exact: true }).first()).toBeVisible();

  await expect(page.getByTestId("mutant")).toHaveCount(demo.eval.mutants.length);
  await expect(page.locator('[data-testid="mutant"][data-state="survived"]')).not.toHaveCount(0);
  await expect(page.locator('[data-split="heldout"] [data-testid="mutant"]')).not.toHaveCount(0);

  await expect(page.getByTestId("curve-line")).toBeVisible();
  await expect(page.getByTestId("threshold")).toBeAttached();
  await expect(page.getByTestId("curve-line")).toHaveAttribute("d", /^M[\d.]+,[\d.]+( L[\d.]+,[\d.]+){3}$/);

  const cards = page.getByTestId("version-card");
  await expect(cards).toHaveCount(4);
  await expect(page.locator('[data-decision="adopted"]')).toHaveCount(2);
  const rolledBack = page.locator('[data-decision="rolled_back"]');
  await expect(rolledBack).toHaveCount(1);
  await expect(rolledBack).toContainText("did not beat");
  await expect(page.locator('[data-decision="baseline"]')).toContainText("v0");
  await expect(rolledBack).toContainText("parent: v1");
  const adoptedColor = await page.locator('.version.adopted').first().evaluate((el) => getComputedStyle(el).borderTopColor);
  const rolledColor = await rolledBack.evaluate((el) => getComputedStyle(el).borderTopColor);
  expect(adoptedColor).not.toBe(rolledColor);
});

test("the header shows provider health", async ({ page }) => {
  await page.goto("/");
  const header = page.getByLabel("API health");
  await expect(header.getByText("anthropic", { exact: true })).toHaveClass(/ok/);
  await expect(header.getByText("gemini")).toHaveClass(/bad/);
});

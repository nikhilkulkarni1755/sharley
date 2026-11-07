import { expect, test } from "@playwright/test";
import { demo, generateTests, mockApi, submitImplementation } from "./mock";

test.beforeEach(({ page }) => mockApi(page));

test("generate tests opens Judge with examples and locked sealed tiles, never any sealed code", async ({ page }) => {
  const request = page.waitForRequest("**/api/banks");
  await generateTests(page);
  expect((await request).postDataJSON()).toEqual({ spec_hash: demo.spec.spec_hash, stack: "docker-api", seed: 0 });

  await expect(page.getByRole("tab", { name: "Judge", selected: true })).toBeVisible();
  const examples = page.getByRole("region", { name: "Example tests" });
  await expect(examples.locator("li")).toHaveCount(12);
  await expect(examples.getByText("test_create_note", { exact: true })).toBeVisible();

  const sealed = page.getByRole("region", { name: "Sealed tests" });
  await expect(sealed.getByTestId("sealed-tile")).toHaveCount(58);
  await expect(sealed.getByTestId("sealed-tile").nth(36)).toContainText("37");
  await expect(sealed.locator("pre, code, details, a, button")).toHaveCount(0);
  for (const ex of demo.bank.examples) await expect(sealed.getByText(ex.name)).toHaveCount(0);

  await examples.getByText("test_create_note", { exact: true }).click();
  await expect(examples.locator("pre code").first()).toContainText("def test_signup_creates_user");
});

test("submitting streams results, flips tiles and shows the verdict", async ({ page }) => {
  await generateTests(page);
  const request = page.waitForRequest("**/api/runs");
  await submitImplementation(page);
  expect((await request).postDataJSON()).toMatchObject({
    bank: demo.bank.key,
    implementer_model: "gpt-5",
    implementer_family: "openai",
    stack: "docker-api",
    files: { "app.py": "# your implementation" },
  });

  const banner = page.getByRole("region", { name: "Verdict" });
  await expect(banner).toContainText("Wrong Answer on sealed test 37 of 58");
  await expect(banner).toContainText("users can read each other's notes");
  await expect(banner).toContainText("12/12 examples passed");
  await expect(banner).toContainText("gpt-5 (openai)");
  await expect(banner).toContainText("claude-sonnet (anthropic)");
  await expect(banner).toContainText("different model families");
  await expect(banner).toContainText(demo.spec.spec_hash);

  const tiles = page.getByTestId("sealed-tile");
  await expect(tiles.nth(36)).toHaveAttribute("data-state", "failed");
  await expect(tiles.nth(0)).toHaveAttribute("data-state", "passed");
  await expect(page.locator('[data-testid="sealed-tile"][data-state="failed"]')).toHaveCount(3);
  await expect(page.locator('[data-testid="sealed-tile"][data-state="passed"]')).toHaveCount(55);
  await expect(page.locator('.examples [data-state="passed"]')).toHaveCount(12);
});

test("tiles flip progressively rather than all at once", async ({ page }) => {
  await generateTests(page);
  await submitImplementation(page);
  await expect(page.locator('[data-testid="sealed-tile"][data-state="pending"]')).not.toHaveCount(58);
  await expect(page.locator('[data-testid="sealed-tile"][data-state="pending"]')).not.toHaveCount(0);
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
});

test("an accepted run renders green", async ({ page }) => {
  await page.unroute("**/api/runs/*/events");
  const accepted = { ...demo.events.at(-1)!, verdict: { ...(demo.events.at(-1) as { verdict: object }).verdict, status: "Accepted" }, summary: "Accepted" };
  await page.route("**/api/runs/*/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: `event: verdict\ndata: ${JSON.stringify(accepted)}\n\n` }),
  );
  await generateTests(page);
  await submitImplementation(page);
  const banner = page.getByRole("region", { name: "Verdict" });
  await expect(banner).toHaveClass(/ok/);
  await expect(banner.getByRole("heading")).toHaveText("Accepted");
});

test("rejected paths are reported", async ({ page }) => {
  await page.unroute("**/api/runs");
  await page.route("**/api/runs", (r) => r.fulfill({ status: 202, json: { run_id: "run1", rejected_paths: ["tests/evil.py"] } }));
  await generateTests(page);
  await submitImplementation(page);
  await expect(page.getByText("Ignored paths (not allowed): tests/evil.py")).toBeVisible();
});

test("replay is the default and animates the stored run; live without a bank explains itself", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Judge" }).click();
  await expect(page.getByRole("button", { name: "Replay", pressed: true })).toBeVisible();
  await expect(page.getByTestId("sealed-tile")).toHaveCount(58);
  await page.getByRole("button", { name: "Play replay" }).click();
  await expect(page.getByRole("region", { name: "Verdict" })).toContainText("Wrong Answer on sealed test 37 of 58");

  await page.getByRole("button", { name: "Live", exact: true }).click();
  await expect(page.getByText(/No test bank yet/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Verdict" })).toHaveCount(0);
  await page.getByRole("button", { name: "Replay", exact: true }).click();
  await expect(page.getByRole("button", { name: "Play replay" })).toBeVisible();
});

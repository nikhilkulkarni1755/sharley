import { expect, test, type Page } from "@playwright/test";
import { alertOf, demo, mockApi, samples, sseBody } from "./mock";

const verdictEvent = demo.events.at(-1) as Extract<(typeof demo.events)[number], { type: "verdict" }>;
const acceptedStream = sseBody([
  ...demo.bank.sealed.map((t) => ({ type: "sealed", index: t.index, passed: true })),
  { ...verdictEvent, verdict: { ...verdictEvent.verdict, status: "Accepted", failed_test_index: null, hint: "" }, summary: "Accepted" },
]);

const editor = (page: Page, path: string) => page.getByRole("textbox", { name: path });
const panel = (page: Page) => page.getByRole("tabpanel", { name: "Playground" });
const tiles = (page: Page) => panel(page).getByTestId("sealed-tile");
const run = (page: Page) => page.getByRole("button", { name: "Run sealed tests" });

test.beforeEach(({ page }) => mockApi(page));

test("opens on the Playground with both backends, the spec, editors and locked tiles", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "Playground", selected: true })).toBeVisible();
  const cards = page.getByRole("group", { name: "Backend" });
  await expect(cards.getByRole("button")).toHaveCount(2);
  await expect(cards.getByText("Payments for users AND AI agents")).toBeVisible();
  await expect(cards.getByText("3 of 12 houses silently get free power")).toBeVisible();

  await page.getByText("Plain-English spec").click();
  await expect(page.getByText(samples[0].spec)).toBeVisible();
  await expect(editor(page, "app/main.py")).toHaveValue(samples[0].files["app/main.py"]);
  await expect(editor(page, "app/db.py")).toBeVisible();
  await expect(page.getByText("the hidden tests never leave the server")).toBeVisible();
  await expect(tiles(page)).toHaveCount(58);
  await expect(tiles(page).first()).toHaveAttribute("data-state", "pending");
  await expect(panel(page).getByRole("region", { name: "Example tests" }).locator("li")).toHaveCount(12);
});

test("Run posts the edited code, flips tiles, shows hint, then an Accepted celebration on the second attempt", async ({ page }) => {
  let streams = 0;
  await page.unroute("**/api/runs/*/events");
  await page.route("**/api/runs/*/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: ++streams === 1 ? sseBody(demo.events) : acceptedStream }),
  );
  await page.goto("/");
  await editor(page, "app/main.py").fill("def pay():\n    return 2\n");

  const request = page.waitForRequest("**/api/runs");
  await run(page).click();
  expect((await request).postDataJSON()).toEqual({
    bank: demo.bank.key,
    implementer_model: "judge-playground",
    implementer_family: "human",
    stack: "docker-api",
    files: { "app/main.py": "def pay():\n    return 2\n", "app/db.py": "DB = {}\n" },
  });

  const banner = page.getByRole("region", { name: "Verdict" });
  await expect(banner).toContainText("Wrong Answer on sealed test 37 of 58");
  await expect(banner.locator(".hint")).toContainText(verdictEvent.verdict.hint);
  await expect(page.locator('[data-testid="sealed-tile"][data-state="failed"]')).toHaveCount(3);
  await expect(page.getByLabel("Attempts")).toHaveText("Attempts: 1");

  await run(page).click();
  await expect(banner).toHaveClass(/ok/);
  await expect(page.locator(".celebrate .cheer")).toContainText("2 attempts");
  await expect(page.locator('[data-testid="sealed-tile"][data-state="passed"]')).toHaveCount(58);
  await expect(page.getByLabel("Attempts")).toHaveText("Attempts: 2");
});

test("Reset code restores the shipped source", async ({ page }) => {
  await page.goto("/");
  await editor(page, "app/main.py").fill("broken");
  await page.getByRole("button", { name: "Reset code" }).click();
  await expect(editor(page, "app/main.py")).toHaveValue(samples[0].files["app/main.py"]);
});

test("a backend without a prepared bank explains itself and disables Run", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Electricity billing/ }).click();
  await expect(page.getByText(/not prepared on this server/)).toBeVisible();
  await expect(run(page)).toBeDisabled();
  await expect(tiles(page)).toHaveCount(0);
});

test("422 same family says to pick a different family", async ({ page }) => {
  await page.unroute("**/api/runs");
  await page.route("**/api/runs", (r) =>
    r.fulfill({ status: 422, json: { detail: "implementer and verifier must be different model families" } }),
  );
  await page.goto("/");
  await run(page).click();
  await expect(alertOf(page)).toContainText("Pick a different family");
});

test("503 is retryable and a network failure is explained", async ({ page }) => {
  let calls = 0;
  await page.unroute("**/api/runs");
  await page.route("**/api/runs", (r) => {
    if (++calls === 1) return r.fulfill({ status: 503, json: { detail: "judge busy" } });
    if (calls === 2) return r.abort();
    return r.fulfill({ status: 202, json: { run_id: "run1", rejected_paths: [] } });
  });
  await page.goto("/");
  await run(page).click();
  await expect(alertOf(page)).toContainText(/provider unavailable, retry/i);
  await alertOf(page).getByRole("button", { name: "Retry" }).click();
  await expect(alertOf(page)).toContainText(/cannot reach the API/i);
  await alertOf(page).getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
});

test("edits survive a reload, per backend", async ({ page }) => {
  await page.goto("/");
  await editor(page, "app/main.py").fill("edited = True");
  await page.reload();
  await expect(editor(page, "app/main.py")).toHaveValue("edited = True");
  await page.getByRole("button", { name: /Electricity billing/ }).click();
  await expect(editor(page, "app/main.py")).toHaveValue(samples[1].files["app/main.py"]);
});

test("Tab indents inside the editor", async ({ page }) => {
  await page.goto("/");
  await editor(page, "app/db.py").fill("x");
  await editor(page, "app/db.py").press("Tab");
  await expect(editor(page, "app/db.py")).toHaveValue("x    ");
});

test("extra fields on sealed entries never reach the page", async ({ page }) => {
  const leaky = {
    ...samples[0],
    bank: {
      ...demo.bank,
      sealed: demo.bank.sealed.map((t) => ({ ...t, locked: true, code: "SECRET_CODE", name: "secret_name", hint: "SECRET_HINT" })),
    },
  };
  await page.unroute("**/api/samples");
  await page.route("**/api/samples", (r) => r.fulfill({ json: [leaky, samples[1]] }));
  await page.goto("/");
  await run(page).click();
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
  const text = await page.locator("body").innerText();
  const html = await page.content();
  for (const secret of ["SECRET_CODE", "secret_name", "SECRET_HINT"]) {
    expect(text).not.toContain(secret);
    expect(html).not.toContain(secret);
  }
});

test("no horizontal scroll at 390px on the Playground", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/");
  await run(page).click();
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

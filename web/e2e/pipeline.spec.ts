import { expect, test, type Page } from "@playwright/test";
import { alertOf, buildSpec, demo, mockApi, sseBody } from "./mock";

const steps = (page: Page) => page.getByRole("list", { name: "Pipeline" }).locator("li");
const generate = (page: Page) => page.getByRole("button", { name: "Generate tests" }).click();
const summary = (page: Page) => page.getByRole("region", { name: "Summary" });

test("steps move pending, running, done and a summary card states the numbers", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  await mockApi(page, { banks: async (r) => { await gate; await r.fulfill({ json: demo.bank }); } });
  await page.goto("/");
  await page.getByRole("tab", { name: "Intake" }).click();
  await expect(steps(page)).toHaveCount(4);
  await expect(steps(page).nth(1)).toHaveAttribute("data-state", "pending");

  await page.getByLabel(/paste a spec/i).fill("Users sign up and keep private notes.");
  await page.getByRole("button", { name: "Build spec" }).click();
  await expect(steps(page).nth(1)).toHaveAttribute("data-state", "done");
  await generate(page);
  await expect(steps(page).nth(2)).toHaveAttribute("data-state", "running");
  release();
  await expect(steps(page).nth(3)).toHaveAttribute("data-state", "done");

  const reqs = demo.spec.requirements;
  const drawn = reqs.filter((r) => r.evidence.kind === "observed").length;
  await expect(summary(page)).toContainText(
    `${reqs.length} requirements (${drawn} drawn, ${reqs.length - drawn} assumed), coverage ${demo.spec.coverage_pct}%, ${demo.bank.examples.length} visible example tests, ${demo.bank.sealed.length} hidden sealed tests`,
  );
  await summary(page).getByRole("button", { name: "Open in Judge" }).click();
  await expect(page.getByRole("tab", { name: "Judge", selected: true })).toBeVisible();
});

test("Start over resets the pipeline", async ({ page }) => {
  await mockApi(page);
  await buildSpec(page);
  await generate(page);
  await summary(page).getByRole("button", { name: "Start over" }).click();
  await expect(summary(page)).toHaveCount(0);
  await expect(steps(page).nth(2)).toHaveAttribute("data-state", "pending");
});

test("an incomplete bank offers a partial bank that re-posts with allow_partial", async ({ page }) => {
  const bodies: unknown[] = [];
  await mockApi(page, {
    banks: (r) => {
      bodies.push(r.request().postDataJSON());
      return bodies.length === 1
        ? r.fulfill({ status: 422, json: { detail: "requirements without tests: ['R9', 'R14']" } })
        : r.fulfill({ json: demo.bank });
    },
  });
  await buildSpec(page);
  await generate(page);
  await expect(alertOf(page)).toContainText("2 requirements could not be tested (R9, R14)");
  await expect(steps(page).nth(2)).toHaveAttribute("data-state", "failed");
  await page.getByRole("button", { name: "Continue with a partial bank" }).click();
  await expect(summary(page)).toContainText("2 requirements untested");
  expect(bodies).toMatchObject([{ allow_partial: false }, { allow_partial: true }]);
});

test("Cancel dismisses the partial prompt", async ({ page }) => {
  await mockApi(page, { banks: (r) => r.fulfill({ status: 422, json: { detail: "requirements without tests: ['R9']" } }) });
  await buildSpec(page);
  await generate(page);
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(alertOf(page)).toHaveCount(0);
});

test("the spend cap is shown plainly with no Retry and fails the Hidden tests step", async ({ page }) => {
  await mockApi(page, { banks: (r) => r.fulfill({ status: 503, json: { detail: "the server's spend cap has been reached; try again tomorrow" } }) });
  await buildSpec(page);
  await generate(page);
  await expect(alertOf(page)).toContainText("the server's spend cap has been reached");
  await expect(alertOf(page).getByRole("button", { name: "Retry" })).toHaveCount(0);
  await expect(steps(page).nth(2)).toHaveAttribute("data-state", "failed");
});

test("repo audit and sealed runs end with a summary card", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "GitHub repo" }).click();
  await page.getByLabel("Repo URL").fill("https://github.com/acme/notes");
  await page.getByRole("button", { name: "Verify repo" }).click();
  await expect(summary(page)).toContainText(/Finished in .*Wrong Answer/);

  await page.unroute("**/api/runs/*/events");
  await page.route("**/api/runs/*/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: sseBody([{ type: "report", total: 10, passed: 7, failed: 3, boot_ok: true, build_output: "" }]) }),
  );
  await page.getByRole("button", { name: "Verify repo" }).click();
  await expect(summary(page)).toContainText(/All done in .*7 of 10 generated tests passed, 3 failures/);
});

test("no horizontal scroll at 390px with the partial prompt and the summary card", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  let calls = 0;
  await mockApi(page, {
    banks: (r) =>
      ++calls === 1 ? r.fulfill({ status: 422, json: { detail: "requirements without tests: ['R9', 'R14', 'R15', 'R16']" } }) : r.fulfill({ json: demo.bank }),
  });
  await buildSpec(page);
  await generate(page);
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await overflow()).toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "Continue with a partial bank" }).click();
  await expect(summary(page)).toBeVisible();
  expect(await overflow()).toBeLessThanOrEqual(0);
});

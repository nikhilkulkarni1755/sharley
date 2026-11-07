import { expect, test } from "@playwright/test";
import { alertOf, buildSpec, demo, generateTests, gotoIntake, mockApi, sseBody, submitImplementation } from "./mock";

test.describe("friendly errors", () => {
  test("503 on intake is a retryable provider message, and retry works", async ({ page }) => {
    let calls = 0;
    await mockApi(page, {
      specs: (route) =>
        ++calls === 1
          ? route.fulfill({ status: 503, json: { detail: "intake failed, please retry: RuntimeError" } })
          : route.fulfill({ json: demo.spec }),
    });
    await buildSpec(page);
    await expect(alertOf(page)).toContainText(/provider unavailable, retry/i);
    await alertOf(page).getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("region", { name: "Spec" })).toBeVisible();
    await expect(alertOf(page)).toHaveCount(0);
  });

  test("422 on an image shows the server's reason", async ({ page }) => {
    await mockApi(page, { image: (r) => r.fulfill({ status: 422, json: { detail: "not a PNG or JPEG" } }) });
    await gotoIntake(page);
    await page.getByLabel("Choose file").setInputFiles({ name: "a.png", mimeType: "image/png", buffer: Buffer.from("junk") });
    await expect(alertOf(page)).toContainText("Invalid input: not a PNG or JPEG");
  });

  test("503 when generating tests is retryable", async ({ page }) => {
    await mockApi(page, { banks: (r) => r.fulfill({ status: 503, json: { detail: "test generation failed, please retry: X" } }) });
    await generateTests(page);
    await expect(alertOf(page)).toContainText(/provider unavailable/i);
    await expect(page.getByRole("tab", { name: "Intake", selected: true })).toBeVisible();
  });

  test("starting a run can fail with 422 and the form keeps its input", async ({ page }) => {
    await mockApi(page, { runs: (r) => r.fulfill({ status: 422, json: { detail: "implementer and verifier must be different model families" } }) });
    await generateTests(page);
    await submitImplementation(page);
    await expect(alertOf(page)).toContainText("different model families");
    await expect(page.getByLabel("Implementer model")).toHaveValue("gpt-5");
  });

  test("an SSE error event surfaces as a message", async ({ page }) => {
    await mockApi(page, {
      events: (r) => r.fulfill({ contentType: "text/event-stream", body: sseBody([{ type: "error", detail: "RuntimeError: sandbox died" }]) }),
    });
    await generateTests(page);
    await submitImplementation(page);
    await expect(alertOf(page)).toContainText("RuntimeError: sandbox died");
    await expect(page.getByRole("button", { name: "Submit implementation" })).toBeEnabled();
  });

  test("invalid file JSON is caught before any request", async ({ page }) => {
    await mockApi(page);
    await generateTests(page);
    await page.getByLabel(/Files/).fill("{nope");
    await page.getByLabel("Implementer model").fill("m");
    await page.getByLabel("Implementer family").fill("f");
    await page.getByRole("button", { name: "Submit implementation" }).click();
    await expect(alertOf(page)).toContainText("valid JSON");
  });

  test("an unreachable demo fixture can be retried", async ({ page }) => {
    let calls = 0;
    await mockApi(page, { demo: (r) => (++calls === 1 ? r.abort() : r.fulfill({ json: demo })) });
    await page.goto("/");
    await page.getByRole("tab", { name: "Eval" }).click();
    const evalPanel = page.getByRole("tabpanel", { name: "Eval" });
    await expect(evalPanel.getByRole("alert")).toContainText(/cannot reach the API/i);
    await evalPanel.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("version-card")).toHaveCount(4);
  });
});

test.describe("accessibility and layout", () => {
  test.beforeEach(({ page }) => mockApi(page));

  test("tabs are keyboard operable", async ({ page }) => {
    await gotoIntake(page);
    const intake = page.getByRole("tab", { name: "Intake" });
    await intake.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Judge" })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Judge" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel", { name: "Judge" })).toBeVisible();
    await page.keyboard.press("End");
    await expect(page.getByRole("tab", { name: "Eval", selected: true })).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Playground", selected: true })).toBeFocused();
    await expect(page.getByRole("tabpanel", { name: "Playground" })).toBeVisible();
  });

  test("the spec can be built from the keyboard alone", async ({ page }) => {
    await gotoIntake(page);
    await page.getByLabel(/paste a spec/i).fill("notes app");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Spec" })).toBeVisible();
  });

  test("no horizontal scroll at 390px on any tab", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await generateTests(page);
    await submitImplementation(page);
    await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
    for (const name of ["Playground", "GitHub repo", "Intake", "Judge", "Eval"]) {
      await page.getByRole("tab", { name }).click();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${name} overflows`).toBeLessThanOrEqual(0);
    }
  });
});

test.describe("security", () => {
  test("extra fields on sealed entries and events are never rendered", async ({ page }) => {
    const bank = {
      ...demo.bank,
      sealed: demo.bank.sealed.map((t) => ({ ...t, code: "assert SECRET_SEALED_CODE", name: "secret_sealed_name", hint: "SECRET_SEALED_HINT", file: "tests/sealed.py" })),
    };
    const leakyEvents = demo.events.map((e) => (e.type === "sealed" ? { ...e, code: "SECRET_EVENT_CODE", name: "SECRET_EVENT_NAME" } : e));
    await mockApi(page, {
      banks: (r) => r.fulfill({ json: bank }),
      events: (r) => r.fulfill({ contentType: "text/event-stream", body: sseBody(leakyEvents) }),
    });
    await generateTests(page);
    await submitImplementation(page);
    await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
    const sealed = page.getByRole("region", { name: "Sealed tests" });
    await expect(sealed).not.toContainText(/SECRET_|secret_sealed/);
    await expect(page.locator("body")).not.toContainText(/SECRET_SEALED|SECRET_EVENT|secret_sealed_name/);
    expect(await page.content()).not.toMatch(/SECRET_SEALED|SECRET_EVENT|secret_sealed_name/);
  });

  test("markup in requirement text and evidence is rendered as text", async ({ page }) => {
    const xss = "<img src=x onerror=\"window.__pwned=1\"><script>window.__pwned=1</script>";
    const spec = {
      ...demo.spec,
      requirements: [{ id: "R1", text: xss, category: "security", evidence: { kind: "observed", source_span: xss, assumption_id: null } }],
      assumptions: {},
    };
    await mockApi(page, { specs: (r) => r.fulfill({ json: spec }) });
    await buildSpec(page);
    const region = page.getByRole("region", { name: "Spec" });
    await expect(region.getByText(xss).first()).toBeVisible();
    await expect(region.locator("img, script")).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
  });

  test("hint text from a verdict is rendered as text", async ({ page }) => {
    const verdict = demo.events.at(-1) as { verdict: object };
    const evil = { ...verdict, type: "verdict", summary: "<b>bold</b> Wrong Answer", rejected_paths: [] };
    await mockApi(page, { events: (r) => r.fulfill({ contentType: "text/event-stream", body: `event: verdict\ndata: ${JSON.stringify(evil)}\n\n` }) });
    await generateTests(page);
    await submitImplementation(page);
    const banner = page.getByRole("region", { name: "Verdict" });
    await expect(banner).toContainText("<b>bold</b> Wrong Answer");
    await expect(banner.locator("b")).toHaveCount(0);
  });
});

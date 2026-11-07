import { expect, test } from "@playwright/test";
import { alertOf, buildSpec, demo, gotoIntake, mockApi } from "./mock";

const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

test.beforeEach(({ page }) => mockApi(page));

test("pasted text becomes requirements with observed and inferred badges and coverage", async ({ page }) => {
  await buildSpec(page);
  const reqs = page.getByRole("region", { name: "Spec" });
  await expect(reqs.getByText("R8", { exact: true })).toBeVisible();
  await expect(reqs.getByText("observed").first()).toBeVisible();
  await expect(reqs.getByText("inferred").first()).toBeVisible();
  await expect(reqs.getByText("sign up with email and password", { exact: true })).toBeVisible();
  await expect(reqs.getByText(/A1: Notes are private to their owner/)).toBeVisible();
  await expect(reqs.getByRole("progressbar", { name: "Coverage" })).toHaveAttribute("aria-valuenow", "88");
  await expect(reqs.getByText("provider: anthropic")).toBeVisible();
  await expect(page.getByLabel("API health").getByText("active: anthropic")).toBeVisible();
});

test("a dropped text file is sent as text", async ({ page }) => {
  await gotoIntake(page);
  const request = page.waitForRequest("**/api/specs");
  await page.getByLabel("Choose file").setInputFiles({ name: "brief.md", mimeType: "text/markdown", buffer: Buffer.from("# Notes API") });
  expect((await request).postDataJSON()).toEqual({ text: "# Notes API" });
  await expect(page.getByRole("region", { name: "Spec" })).toBeVisible();
});

test("a dropped image shows the tracing animation, then the spec", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.unroute("**/api/specs/image");
  await page.route("**/api/specs/image", async (route) => {
    await gate;
    await route.fulfill({ json: demo.spec });
  });
  const request = page.waitForRequest("**/api/specs/image");
  await gotoIntake(page);
  const dt = await page.evaluateHandle((b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const data = new DataTransfer();
    data.items.add(new File([bytes], "shot.png", { type: "image/png" }));
    return data;
  }, PNG_B64);
  await page.locator(".drop").dispatchEvent("drop", { dataTransfer: dt });

  await expect(page.getByTestId("trace")).toBeVisible();
  await expect(page.getByAltText("Uploaded spec screenshot")).toBeVisible();
  release();
  await expect(page.getByRole("region", { name: "Spec" })).toBeVisible();
  await expect(page.getByTestId("trace")).toHaveCount(0);
  const body = (await request).postDataJSON();
  expect(body.image_b64).toBe(PNG_B64);
  expect(body.image_b64).not.toContain("data:");
});

test("unsupported files get a friendly message", async ({ page }) => {
  await gotoIntake(page);
  await page.getByLabel("Choose file").setInputFiles({ name: "x.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  await expect(alertOf(page)).toContainText("text file or a PNG/JPEG");
});

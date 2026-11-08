import { expect, test, type Page } from "@playwright/test";
import { buildSpec, demo, gotoIntake, mockApi } from "./mock";

const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";
const FILE = /^sharley-project-b41e07d9\.zip$/;
const button = (page: Page) => page.getByRole("button", { name: /Download project|Preparing zip/ });

async function photoFlow(page: Page) {
  await gotoIntake(page);
  await page.getByLabel("Choose file").setInputFiles({ name: "s.png", mimeType: "image/png", buffer: Buffer.from(PNG_B64, "base64") });
  await page.getByRole("button", { name: "Generate tests" }).click();
}

test("photo flow downloads automatically with image_b64", async ({ page }) => {
  await mockApi(page);
  const download = page.waitForEvent("download");
  const request = page.waitForRequest("**/api/banks/*/project");
  await photoFlow(page);
  expect((await download).suggestedFilename()).toMatch(FILE);
  const req = await request;
  expect(req.url()).toContain(`/api/banks/${encodeURIComponent(demo.bank.key)}/project`);
  expect(req.postDataJSON()).toEqual({ image_b64: PNG_B64 });
  await expect(button(page)).toHaveText("Download project (.zip)");
});

test("text flow only downloads on click, without image_b64", async ({ page }) => {
  let posts = 0;
  await mockApi(page, { project: (r) => (posts++, r.fulfill({ contentType: "application/zip", body: Buffer.from("PK") })) });
  await buildSpec(page);
  await page.getByRole("button", { name: "Generate tests" }).click();
  await expect(button(page)).toBeVisible();
  await expect(page.getByText("Hidden tests are never included.")).toBeVisible();
  expect(posts).toBe(0);
  const download = page.waitForEvent("download");
  const request = page.waitForRequest("**/api/banks/*/project");
  await button(page).click();
  expect((await download).suggestedFilename()).toMatch(FILE);
  expect((await request).postDataJSON()).toEqual({});
});

for (const status of [404, 422]) {
  test(`a ${status} shows an inline error with Retry and keeps the summary`, async ({ page }) => {
    let calls = 0;
    await mockApi(page, {
      project: (r) => (++calls === 1 ? r.fulfill({ status, json: { detail: "nope" } }) : r.fulfill({ contentType: "application/zip", body: Buffer.from("PK") })),
    });
    await buildSpec(page);
    await page.getByRole("button", { name: "Generate tests" }).click();
    await button(page).click();
    const summary = page.getByRole("region", { name: "Summary" });
    await expect(summary.getByRole("alert")).toContainText("nope");
    await expect(summary).toContainText(/All done in/);
    await expect(summary.getByRole("button", { name: "Open in Judge" })).toBeVisible();
    const download = page.waitForEvent("download");
    await summary.getByRole("button", { name: "Retry" }).click();
    await download;
    await expect(summary.getByRole("alert")).toHaveCount(0);
  });
}

test("double click starts one download", async ({ page }) => {
  let posts = 0;
  await mockApi(page, {
    project: async (r) => {
      posts++;
      await new Promise((resolve) => setTimeout(resolve, 300));
      await r.fulfill({ contentType: "application/zip", body: Buffer.from("PK") });
    },
  });
  await buildSpec(page);
  await page.getByRole("button", { name: "Generate tests" }).click();
  await button(page).dblclick();
  await expect(button(page)).toHaveText("Download project (.zip)");
  expect(posts).toBe(1);
});

test("no horizontal scroll at 390px with the download card", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await mockApi(page);
  await buildSpec(page);
  await page.getByRole("button", { name: "Generate tests" }).click();
  await expect(button(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

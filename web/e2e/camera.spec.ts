import { expect, test, type Page } from "@playwright/test";
import { alertOf, gotoIntake, mockApi } from "./mock";

declare global {
  interface Window {
    __stopped: number;
  }
}

/** Replaces getUserMedia with a canvas-backed MediaStream whose tracks count their stop() calls. */
const stubCamera = (page: Page, mode: "ok" | "denied") =>
  page.addInitScript((m) => {
    window.__stopped = 0;
    const fake = {
      getUserMedia: async () => {
        if (m === "denied") throw new DOMException("denied", "NotAllowedError");
        const canvas = document.createElement("canvas");
        canvas.width = 64;
        canvas.height = 48;
        const ctx = canvas.getContext("2d")!;
        setInterval(() => {
          ctx.fillStyle = "#c33";
          ctx.fillRect(0, 0, 64, 48);
        }, 30);
        const stream = canvas.captureStream(30);
        stream.getTracks().forEach((t) => {
          const stop = t.stop.bind(t);
          t.stop = () => {
            window.__stopped++;
            stop();
          };
        });
        return stream;
      },
    };
    Object.defineProperty(navigator, "mediaDevices", { value: fake, configurable: true });
  }, mode);

test.beforeEach(({ page }) => mockApi(page));

test("webcam capture posts a base64 PNG through the image path and stops the tracks", async ({ page }) => {
  await stubCamera(page, "ok");
  await gotoIntake(page);
  await page.getByRole("button", { name: "Use webcam" }).click();
  await expect(page.getByLabel("Webcam preview")).toBeVisible();
  await expect.poll(() => page.getByLabel("Webcam preview").evaluate((v: HTMLVideoElement) => v.videoWidth)).toBeGreaterThan(0);

  const request = page.waitForRequest("**/api/specs/image");
  await page.getByRole("button", { name: "Capture" }).click();
  const body = (await request).postDataJSON();
  expect(body.image_b64.startsWith("iVBOR")).toBe(true);
  await expect(page.getByRole("region", { name: "Spec" })).toBeVisible();
  expect(await page.evaluate(() => window.__stopped)).toBeGreaterThan(0);
  await expect(page.getByLabel("Webcam preview")).toHaveCount(0);
});

test("cancelling the webcam stops the tracks", async ({ page }) => {
  await stubCamera(page, "ok");
  await gotoIntake(page);
  await page.getByRole("button", { name: "Use webcam" }).click();
  await expect(page.getByLabel("Webcam preview")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByLabel("Webcam preview")).toHaveCount(0);
  expect(await page.evaluate(() => window.__stopped)).toBeGreaterThan(0);
});

test("permission denied explains itself and file upload still works", async ({ page }) => {
  await stubCamera(page, "denied");
  await gotoIntake(page);
  await page.getByRole("button", { name: "Use webcam" }).click();
  await expect(alertOf(page)).toContainText("permission denied");
  await expect(page.getByLabel("Webcam preview")).toHaveCount(0);

  const request = page.waitForRequest("**/api/specs");
  await page.getByLabel("Choose file").setInputFiles({ name: "brief.md", mimeType: "text/markdown", buffer: Buffer.from("# Notes") });
  await request;
});

test("Take a photo opens the camera on phones and feeds the same path", async ({ page }) => {
  await gotoIntake(page);
  const photo = page.getByLabel("Take a photo");
  await expect(photo).toHaveAttribute("capture", "environment");
  await expect(photo).toHaveAttribute("accept", "image/*");
  const request = page.waitForRequest("**/api/specs/image");
  await photo.setInputFiles({ name: "p.png", mimeType: "image/png", buffer: Buffer.from("png") });
  await request;
});

test("non-images and oversized images are rejected client-side", async ({ page }) => {
  let posted = false;
  await page.route("**/api/specs/image", (r) => ((posted = true), r.abort()));
  await gotoIntake(page);
  await page.getByLabel("Take a photo").setInputFiles({ name: "a.gif", mimeType: "image/gif", buffer: Buffer.from("GIF") });
  await expect(alertOf(page)).toContainText("PNG/JPEG");
  await page.getByLabel("Take a photo").setInputFiles({ name: "big.png", mimeType: "image/png", buffer: Buffer.alloc(8_000_001) });
  await expect(alertOf(page)).toContainText("8 MB");
  expect(posted).toBe(false);
});

test("the sample sketch runs the image flow in one click", async ({ page }) => {
  await gotoIntake(page);
  const request = page.waitForRequest("**/api/specs/image");
  await page.getByRole("button", { name: "Try the sample sketch" }).click();
  expect((await request).postDataJSON().image_b64.startsWith("iVBOR")).toBe(true);
  await expect(page.getByRole("region", { name: "Spec" })).toBeVisible();
});

test("no horizontal scroll at 390px on Intake with the camera controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await gotoIntake(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

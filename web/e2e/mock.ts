import { readFileSync } from "node:fs";
import path from "node:path";
import type { Page, Route } from "@playwright/test";
import type { Demo, Sample } from "../lib/types";

export const demo: Demo = JSON.parse(readFileSync(path.join(__dirname, "../fixtures/demo.sample.json"), "utf8"));

export const health = { status: "ok", offline: false, providers: { anthropic: true, gemini: false }, active_provider: "anthropic" };

export const samples: Sample[] = [
  {
    name: "payments",
    title: "Payments API",
    spec: "Users and AI agents can pay each other.",
    files: { "app/main.py": "def pay():\n    return 1\n", "app/db.py": "DB = {}\n" },
    bank: demo.bank,
  },
  { name: "electricity", title: "Electricity billing", spec: "Bill every house by usage.", files: { "app/main.py": "def bill():\n    return 0\n" }, bank: null },
];

export const sseBody = (events: object[]) =>
  events.map((e) => `event: ${(e as { type: string }).type}\ndata: ${JSON.stringify(e)}\n\n`).join("");

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body });

export interface Overrides {
  specs?: (route: Route) => Promise<void> | void;
  image?: (route: Route) => Promise<void> | void;
  banks?: (route: Route) => Promise<void> | void;
  runs?: (route: Route) => Promise<void> | void;
  events?: (route: Route) => Promise<void> | void;
  samples?: (route: Route) => Promise<void> | void;
  demo?: (route: Route) => Promise<void> | void;
}

/** Serves the whole API from the sample fixture; any endpoint can be swapped out per test. */
export async function mockApi(page: Page, o: Overrides = {}) {
  await page.route("**/api/health", (r) => json(r, health));
  await page.route("**/api/samples", o.samples ?? ((r) => json(r, samples)));
  await page.route("**/api/demo", o.demo ?? ((r) => json(r, demo)));
  await page.route("**/api/specs", o.specs ?? ((r) => json(r, demo.spec)));
  await page.route("**/api/specs/image", o.image ?? ((r) => json(r, demo.spec)));
  await page.route("**/api/banks", o.banks ?? ((r) => json(r, demo.bank)));
  await page.route("**/api/runs", o.runs ?? ((r) => json(r, { run_id: "run1", rejected_paths: [] }, 202)));
  await page.route(
    "**/api/runs/*/events",
    o.events ?? ((r) => r.fulfill({ status: 200, contentType: "text/event-stream", body: sseBody(demo.events) })),
  );
}

/** Page alerts, excluding Next's empty route announcer. */
export const alertOf = (page: Page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');

export async function gotoIntake(page: Page) {
  await page.goto("/");
  await page.getByRole("tab", { name: "Intake" }).click();
}

export async function buildSpec(page: Page) {
  await gotoIntake(page);
  await page.getByLabel(/paste a spec/i).fill("Users sign up and keep private notes.");
  await page.getByRole("button", { name: "Build spec" }).click();
}

export async function generateTests(page: Page) {
  await buildSpec(page);
  await page.getByRole("button", { name: "Generate tests" }).click();
}

export async function submitImplementation(page: Page) {
  await page.getByLabel("Implementer model").fill("gpt-5");
  await page.getByLabel("Implementer family").fill("openai");
  await page.getByRole("button", { name: "Submit implementation" }).click();
}

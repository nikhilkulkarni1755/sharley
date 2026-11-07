import type { Bank, Spec } from "./types";

export type StepState = "pending" | "running" | "done" | "failed";

export interface Step {
  state: StepState;
  ms?: number;
  reason?: string;
}

export const STEP_LABELS = ["Read input", "Requirements", "Hidden tests", "Ready to judge"];

export const idleSteps = (): Step[] => STEP_LABELS.map(() => ({ state: "pending" }));

export const withStep = (steps: Step[], index: number, step: Step): Step[] => steps.map((s, i) => (i === index ? step : s));

/** "<1 s", "17 s", "1m 12s". */
export function formatElapsed(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (ms < 1000) return "<1 s";
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

export const totalMs = (steps: Step[]): number => steps.reduce((sum, s) => sum + (s.ms ?? 0), 0);

/** The numbers the final card states, taken from the API responses. */
export function summaryCounts(spec: Spec, bank: Bank) {
  const drawn = spec.requirements.filter((r) => r.evidence.kind === "observed").length;
  return {
    requirements: spec.requirements.length,
    drawn,
    assumed: spec.requirements.length - drawn,
    coverage: spec.coverage_pct,
    examples: bank.examples.length,
    sealed: bank.sealed.length,
  };
}

export const summaryText = (spec: Spec, bank: Bank, ms: number): string => {
  const c = summaryCounts(spec, bank);
  return `All done in ${formatElapsed(ms)}: ${c.requirements} requirements (${c.drawn} drawn, ${c.assumed} assumed), coverage ${c.coverage}%, ${c.examples} visible example tests, ${c.sealed} hidden sealed tests`;
};

const MISSING = "requirements without tests:";
export const SPEND_CAP = "the server's spend cap has been reached";

/** Requirement ids from a 422 "requirements without tests: ['R9', 'R14']"; null for any other detail. */
export function untestedIds(detail: unknown): string[] | null {
  if (typeof detail !== "string" || !detail.startsWith(MISSING)) return null;
  return [...detail.slice(MISSING.length).matchAll(/['"]([^'"]+)['"]/g)].map((m) => m[1]);
}

export const isSpendCap = (detail: unknown): boolean => typeof detail === "string" && detail.startsWith(SPEND_CAP);

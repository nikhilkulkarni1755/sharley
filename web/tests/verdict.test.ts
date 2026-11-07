import { describe, expect, it } from "vitest";
import type { Status, Verdict } from "../lib/types";
import { examplesLine, hidesFailures, isIndependent, sealedLine, verdictHeadline, verdictTone } from "../lib/verdict";

const base = {
  example_passed: 12,
  example_total: 12,
  total_sealed: 60,
  status: "Wrong Answer",
  implementer: { model: "a", family: "openai" },
  verifier: { model: "b", family: "anthropic" },
} as Verdict;

describe("verdict formatting", () => {
  it("prefers the server summary and falls back to the status", () => {
    expect(verdictHeadline("Wrong Answer", "Wrong Answer on sealed test 37 of 58: x (R8)")).toContain("sealed test 37 of 58");
    expect(verdictHeadline("Accepted", "")).toBe("Accepted");
  });

  it("maps every status to a tone", () => {
    const tones: Record<Status, string> = {
      Accepted: "ok",
      "Wrong Answer": "bad",
      "Runtime Error": "bad",
      "Time Limit Exceeded": "warn",
      "Build Failed": "warn",
      "Rejected: tests tampered": "bad",
    };
    for (const [status, tone] of Object.entries(tones)) expect(verdictTone(status as Status)).toBe(tone);
  });

  it("formats the visible and sealed lines from streamed results", () => {
    const sealed = { 1: true, 2: true, 3: false };
    expect(examplesLine(base)).toBe("Visible examples: 12/12 passed");
    expect(sealedLine(base, sealed)).toBe("Hidden sealed tests: 2/60 passed");
    expect(hidesFailures(base, sealed)).toBe(true);
    expect(hidesFailures({ ...base, example_passed: 11 }, sealed)).toBe(false);
    expect(hidesFailures(base, { 1: true })).toBe(false);
  });

  it("falls back to the verdict when no sealed results streamed", () => {
    expect(sealedLine({ ...base, status: "Accepted" }, {})).toBe("Hidden sealed tests: 60/60 passed");
    expect(sealedLine(base, {})).toBe("Hidden sealed tests: 0/60 passed");
  });

  it("flags same-family runs as not independent", () => {
    expect(isIndependent(base)).toBe(true);
    expect(isIndependent({ ...base, verifier: { model: "b", family: "openai" } })).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import type { Status, Verdict } from "../lib/types";
import { examplesLine, isIndependent, verdictHeadline, verdictTone } from "../lib/verdict";

const base = {
  example_passed: 12,
  example_total: 12,
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

  it("formats the example line", () => {
    expect(examplesLine(base)).toBe("12/12 examples passed");
  });

  it("flags same-family runs as not independent", () => {
    expect(isIndependent(base)).toBe(true);
    expect(isIndependent({ ...base, verifier: { model: "b", family: "openai" } })).toBe(false);
  });
});

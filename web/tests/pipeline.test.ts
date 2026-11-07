import { describe, expect, it } from "vitest";
import { formatElapsed, idleSteps, isSpendCap, summaryCounts, totalMs, untestedIds, withStep } from "../lib/pipeline";
import type { Bank, Spec } from "../lib/types";

describe("formatElapsed", () => {
  it("formats sub-second, seconds and minutes", () => {
    expect(formatElapsed(400)).toBe("<1 s");
    expect(formatElapsed(17_400)).toBe("17 s");
    expect(formatElapsed(72_000)).toBe("1m 12s");
    expect(formatElapsed(125_000)).toBe("2m 05s");
  });
});

describe("summaryCounts", () => {
  it("splits requirements into drawn and assumed and counts both test kinds", () => {
    const req = (kind: "observed" | "inferred") => ({ id: "R", text: "", category: "functional", evidence: { kind, source_span: null, assumption_id: null } });
    const spec = { requirements: [req("observed"), req("observed"), req("inferred")], coverage_pct: 100 } as Spec;
    const bank = { examples: [1, 2], sealed: [1, 2, 3, 4] } as unknown as Bank;
    expect(summaryCounts(spec, bank)).toEqual({ requirements: 3, drawn: 2, assumed: 1, coverage: 100, examples: 2, sealed: 4 });
  });
});

describe("pipeline steps", () => {
  it("replaces one step and sums the elapsed time", () => {
    const steps = withStep(withStep(idleSteps(), 1, { state: "done", ms: 1000 }), 2, { state: "done", ms: 2500 });
    expect(steps.map((s) => s.state)).toEqual(["pending", "done", "done", "pending"]);
    expect(totalMs(steps)).toBe(3500);
  });
});

describe("server detail parsing", () => {
  it("extracts untested requirement ids", () => {
    expect(untestedIds("requirements without tests: ['R9', 'R14']")).toEqual(["R9", "R14"]);
    expect(untestedIds("something else")).toBeNull();
    expect(untestedIds(undefined)).toBeNull();
  });

  it("recognises the spend cap", () => {
    expect(isSpendCap("the server's spend cap has been reached; try later")).toBe(true);
    expect(isSpendCap("please retry")).toBe(false);
  });
});

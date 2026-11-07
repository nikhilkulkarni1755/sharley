import { describe, expect, it } from "vitest";
import { buildCurve, THRESHOLD } from "../lib/curve";
import type { SkillVersion } from "../lib/types";

const v = (version: number, pw: number | null): SkillVersion => ({
  version,
  parent: version ? version - 1 : null,
  rules: [],
  diff: "",
  scores: pw === null ? null : { heldout_mutation_score: pw, false_failure_rate: 0, security_kill_rate: 0, production_worthy: pw },
  decision: version ? "adopted" : "baseline",
  reason: "",
});

describe("buildCurve", () => {
  it("places high scores near the top and spreads versions across the width", () => {
    const c = buildCurve([v(0, 0.5), v(1, 1)], 100, 100, 10);
    expect(c.points.map((p) => p.x)).toEqual([10, 90]);
    expect(c.points.map((p) => p.y)).toEqual([50, 10]);
    expect(c.path).toBe("M10.0,50.0 L90.0,10.0");
  });

  it("puts the threshold line at 0.90", () => {
    expect(buildCurve([v(0, 0.5)], 100, 100, 10).thresholdY).toBeCloseTo(10 + (1 - THRESHOLD) * 80);
  });

  it("skips unscored versions and centres a single point", () => {
    const c = buildCurve([v(0, null), v(1, 0.5)], 100, 100, 10);
    expect(c.points).toHaveLength(1);
    expect(c.points[0].x).toBe(50);
  });

  it("returns an empty path when nothing is scored", () => {
    expect(buildCurve([v(0, null)], 100, 100, 10).path).toBe("");
  });
});

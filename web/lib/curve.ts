import type { SkillVersion } from "./types";

export const THRESHOLD = 0.9;

export interface Point {
  x: number;
  y: number;
  version: SkillVersion;
}

export interface Curve {
  points: Point[];
  path: string;
  thresholdY: number;
}

/** Maps each scored version's production-worthy score onto an SVG box (y axis spans 0..1, higher is up). */
export function buildCurve(timeline: SkillVersion[], width: number, height: number, pad: number): Curve {
  const scored = timeline.filter((v) => v.scores !== null);
  const innerW = width - 2 * pad;
  const innerH = height - 2 * pad;
  const yOf = (score: number) => pad + (1 - score) * innerH;
  const points = scored.map((version, i) => ({
    x: pad + (scored.length > 1 ? (i / (scored.length - 1)) * innerW : innerW / 2),
    y: yOf(version.scores!.production_worthy),
    version,
  }));
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  return { points, path, thresholdY: yOf(THRESHOLD) };
}

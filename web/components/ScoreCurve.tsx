import { buildCurve, THRESHOLD } from "../lib/curve";
import type { SkillVersion } from "../lib/types";

const W = 480;
const H = 200;
const PAD = 32;

export default function ScoreCurve({ timeline }: { timeline: SkillVersion[] }) {
  const { points, path, thresholdY } = buildCurve(timeline, W, H, PAD);
  return (
    <section className="panel" aria-label="Score curve">
      <h3>Held-out production-worthy score per skill version</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="curve" role="img" aria-label="Score curve per skill version">
        <line x1={PAD} x2={W - PAD} y1={thresholdY} y2={thresholdY} className="threshold" data-testid="threshold" />
        <text x={PAD} y={thresholdY - 5} className="axis">
          threshold {THRESHOLD.toFixed(2)}
        </text>
        <path d={path} pathLength={1} className="line" data-testid="curve-line" />
        {points.map((p) => (
          <g key={p.version.version} className={p.version.decision}>
            <circle cx={p.x} cy={p.y} r={5} />
            <text x={p.x} y={H - 8} textAnchor="middle" className="axis">
              v{p.version.version}
            </text>
            <text x={p.x} y={p.y - 10} textAnchor="middle" className="axis">
              {p.version.scores!.production_worthy.toFixed(2)}
            </text>
          </g>
        ))}
      </svg>
    </section>
  );
}

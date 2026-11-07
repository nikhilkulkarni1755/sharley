import { THRESHOLD } from "../lib/curve";
import type { Demo } from "../lib/types";
import MutantGrid from "./MutantGrid";
import SourceChip from "./SourceChip";
import ScoreCurve from "./ScoreCurve";
import Timeline from "./Timeline";

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

export default function Eval({ demo }: { demo: Demo }) {
  const { scores, reference } = demo.eval;
  const cards: [string, string][] = [
    ["Held-out mutation score", pct(scores.heldout_mutation_score)],
    ["False failure rate", pct(scores.false_failure_rate)],
    ["Security kill rate", pct(scores.security_kill_rate)],
    ["Production-worthy", scores.production_worthy.toFixed(3)],
  ];
  return (
    <div className="stack">
      <h2>Eval</h2>
      <SourceChip kind="recorded" meta={demo.meta} />
      <p>Real Docker runs of the notes reference app; the test writer was a scripted stand-in, not a model.</p>
      <ul className="scores">
        {cards.map(([label, value]) => (
          <li key={label} className={label === "Production-worthy" && scores.production_worthy >= THRESHOLD ? "ok" : undefined}>
            <small>{label}</small>
            <b>{value}</b>
          </li>
        ))}
      </ul>
      <p className="muted">Reference app: {reference.failed} of {reference.tests} tests failed (false failures).</p>
      <MutantGrid mutants={demo.eval.mutants} />
      <ScoreCurve timeline={demo.timeline} />
      <Timeline timeline={demo.timeline} />
    </div>
  );
}

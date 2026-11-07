import type { SkillVersion } from "../lib/types";

const LABELS = { baseline: "baseline", adopted: "adopted", rolled_back: "rolled back" };

export default function Timeline({ timeline }: { timeline: SkillVersion[] }) {
  return (
    <section aria-label="Skill versions">
      <h3>Skill versions</h3>
      <ol className="timeline">
        {timeline.map((v) => (
          <li key={v.version} className={`version ${v.decision}`} data-testid="version-card" data-decision={v.decision}>
            <div className="row between">
              <strong>v{v.version}</strong>
              <span className={`badge ${v.decision}`}>{LABELS[v.decision]}</span>
            </div>
            <p className="muted">parent: {v.parent === null ? "none" : `v${v.parent}`}</p>
            {v.scores && (
              <p>
                held-out {v.scores.heldout_mutation_score.toFixed(2)} · false failures {v.scores.false_failure_rate.toFixed(2)} · security{" "}
                {v.scores.security_kill_rate.toFixed(2)} · production-worthy {v.scores.production_worthy.toFixed(3)}
              </p>
            )}
            {v.rules.length > 0 && (
              <ul>
                {v.rules.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            {v.diff && <pre><code>{v.diff}</code></pre>}
            {v.reason && <p className="reason">{v.reason}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

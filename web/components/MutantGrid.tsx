import type { Mutant } from "../lib/types";

const stateOf = (m: Mutant) => (m.killed === null ? "unrun" : m.killed ? "killed" : "survived");

function Lane({ split, mutants }: { split: Mutant["split"]; mutants: Mutant[] }) {
  const killed = mutants.filter((m) => m.killed).length;
  return (
    <div className="lane" data-split={split}>
      <h4>
        {split === "train" ? "Train" : "Held-out"} <span className="muted">{killed}/{mutants.length} killed</span>
      </h4>
      <div className="dots">
        {mutants.map((m, i) => (
          <span
            key={m.id}
            className={`mutant ${stateOf(m)} ${m.category}`}
            data-testid="mutant"
            data-state={stateOf(m)}
            title={`${m.id} ${m.operator} (${m.category}): ${stateOf(m)}`}
            style={{ animationDelay: `${i * 18}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export default function MutantGrid({ mutants }: { mutants: Mutant[] }) {
  return (
    <section className="panel" aria-label="Mutants">
      <h3>Mutants</h3>
      <div className="legend muted">
        <span className="mutant killed" /> killed <span className="mutant survived" /> survived <span className="mutant unrun" /> not run · security mutants have a ring
      </div>
      {(["train", "heldout"] as const).map((split) => (
        <Lane key={split} split={split} mutants={mutants.filter((m) => m.split === split)} />
      ))}
    </section>
  );
}

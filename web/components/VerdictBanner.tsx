import type { RunEvent } from "../lib/types";
import { examplesLine, isIndependent, verdictHeadline, verdictTone } from "../lib/verdict";

export default function VerdictBanner({ event }: { event: Extract<RunEvent, { type: "verdict" }> }) {
  const v = event.verdict;
  return (
    <section className={`verdict ${verdictTone(v.status)}`} aria-label="Verdict">
      <h3>{verdictHeadline(v.status, event.summary)}</h3>
      <p>{examplesLine(v)}</p>
      <dl>
        <div>
          <dt>Implementer</dt>
          <dd>{v.implementer.model} ({v.implementer.family})</dd>
        </div>
        <div>
          <dt>Verifier</dt>
          <dd>{v.verifier.model} ({v.verifier.family})</dd>
        </div>
        <div>
          <dt>Independence</dt>
          <dd>{isIndependent(v) ? "different model families" : "same family: not independent"}</dd>
        </div>
        <div>
          <dt>Seed</dt>
          <dd>{v.seed}</dd>
        </div>
        <div>
          <dt>Spec hash</dt>
          <dd className="mono">{v.spec_hash}</dd>
        </div>
      </dl>
    </section>
  );
}

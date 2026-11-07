import type { RunEvent } from "../lib/types";
import { examplesLine, hidesFailures, isIndependent, sealedLine, verdictHeadline, verdictTone } from "../lib/verdict";

export default function VerdictBanner({ event, sealed }: { event: Extract<RunEvent, { type: "verdict" }>; sealed: Record<number, boolean> }) {
  const v = event.verdict;
  return (
    <section className={`verdict ${verdictTone(v.status)}`} aria-label="Verdict">
      <h3>{verdictHeadline(v.status, event.summary)}</h3>
      {v.hint && <p className="hint">{v.hint}</p>}
      <p>{examplesLine(v)}</p>
      <p>{sealedLine(v, sealed)}</p>
      {hidesFailures(v, sealed) && <p className="hint">Passes everything you can see but fails hidden tests</p>}
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

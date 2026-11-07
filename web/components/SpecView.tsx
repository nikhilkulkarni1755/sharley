import type { Requirement, Spec } from "../lib/types";

function Evidence({ req, assumptions }: { req: Requirement; assumptions: Spec["assumptions"] }) {
  const { kind, source_span, assumption_id } = req.evidence;
  return kind === "observed" ? (
    <p className="evidence">
      <span className="badge ok">observed</span> <q>{source_span}</q>
    </p>
  ) : (
    <p className="evidence">
      <span className="badge warn">inferred</span> {assumption_id}: {assumption_id && assumptions[assumption_id]}
    </p>
  );
}

export default function SpecView({ spec, busy, onGenerate }: { spec: Spec; busy: boolean; onGenerate: () => void }) {
  return (
    <section className="panel" aria-label="Spec">
      <div className="row between">
        <h2>Spec</h2>
        {spec.active_provider && <span className="chip">provider: {spec.active_provider}</span>}
      </div>
      <div className="coverage">
        <span>Coverage {Math.round(spec.coverage_pct)}%</span>
        <div className="bar" role="progressbar" aria-label="Coverage" aria-valuenow={Math.round(spec.coverage_pct)} aria-valuemin={0} aria-valuemax={100}>
          <div style={{ width: `${spec.coverage_pct}%` }} />
        </div>
      </div>
      <ul className="reqs">
        {spec.requirements.map((r) => (
          <li key={r.id}>
            <div className="row">
              <strong>{r.id}</strong>
              <span className="chip">{r.category}</span>
              <span>{r.text}</span>
            </div>
            <Evidence req={r} assumptions={spec.assumptions} />
          </li>
        ))}
      </ul>
      {spec.ignored.length > 0 && (
        <details>
          <summary>{spec.ignored.length} ignored span(s)</summary>
          <ul>
            {spec.ignored.map((s) => (
              <li key={s.span}>
                <q>{s.span}</q> <span className="muted">{s.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <button className="primary" disabled={busy} onClick={onGenerate}>
        Generate tests
      </button>
    </section>
  );
}

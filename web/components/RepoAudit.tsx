import { STAGES, stepState } from "../lib/repo";
import type { RunState } from "../lib/run";

const clip = (text: string) => (text.length > 300 ? `${text.slice(0, 300)}…` : text);

export default function RepoAudit({ state, running }: { state: RunState; running: boolean }) {
  const { stage, surface, findings, report } = state;
  return (
    <>
      <ol className="stepper" aria-label="Progress">
        {STAGES.map((s, i) => (
          <li key={s.id} data-state={stepState(i, stage?.stage ?? null, !running)}>
            {s.label}
          </li>
        ))}
      </ol>
      {stage && running && <p className="muted" role="status">{stage.detail}</p>}
      {surface && (
        <ul className="scores" aria-label="Repo surface">
          {(
            [
              ["files", surface.files],
              ["routes", surface.routes],
              ["env vars", surface.env_vars],
              ["stack", surface.stack ?? "unknown"],
            ] as const
          ).map(([label, value]) => (
            <li key={label}>
              <small>{label}</small>
              <b>{value}</b>
            </li>
          ))}
        </ul>
      )}
      {findings.map((f) => (
        <details key={f.id} className="panel finding">
          <summary>
            <strong>{f.name}</strong>
            <span className="badge warn">{f.family}</span>
            {f.requirement_ids.map((id) => (
              <span key={id} className="chip">{id}</span>
            ))}
          </summary>
          <p>{f.requirement_text}</p>
          <pre><code>{clip(f.message)}</code></pre>
        </details>
      ))}
      {report && (
        <section className="panel stack" aria-label="Report">
          {report.boot_ok ? (
            <>
              <h3>{report.passed} of {report.total} generated tests passed</h3>
              <div role="progressbar" aria-valuenow={report.passed} aria-valuemin={0} aria-valuemax={report.total} className="bar">
                <span style={{ width: `${report.total ? (report.passed / report.total) * 100 : 0}%` }} />
              </div>
            </>
          ) : (
            <>
              <h3>Could not start this repo with the standard runner</h3>
              <p className="muted">The sandbox has no network and a fixed set of Python libraries, so repos that need others cannot boot.</p>
              <details>
                <summary>Build output</summary>
                <pre><code>{report.build_output}</code></pre>
              </details>
            </>
          )}
        </section>
      )}
    </>
  );
}

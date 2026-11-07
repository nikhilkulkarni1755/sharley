import { tileState } from "../lib/run";
import type { ExampleTest } from "../lib/types";

export default function ExampleList({ examples, results }: { examples: ExampleTest[]; results: Record<string, boolean> }) {
  return (
    <section aria-label="Example tests" className="panel">
      <h3>Example tests <span className="muted">visible to the implementer</span></h3>
      <ul className="examples">
        {examples.map((t) => (
          <li key={t.id} data-state={tileState(results, t.id)}>
            <details>
              <summary>
                <span className="status" aria-hidden="true" />
                <span className="name">{t.name}</span>
                <span className="chip">{t.family}</span>
                <span className="muted">{t.requirement_ids.join(", ")}</span>
              </summary>
              <pre><code>{t.code}</code></pre>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

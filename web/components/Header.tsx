import type { Health } from "../lib/types";

export default function Header({ health }: { health: Health | null }) {
  return (
    <header className="top">
      <div>
        <h1>Sharley</h1>
        <p className="muted">Independent verifier: example tests are shown, sealed tests decide.</p>
      </div>
      <ul className="health" aria-label="API health">
        {health === null ? (
          <li className="chip bad">API unreachable</li>
        ) : (
          <>
            {Object.entries(health.providers).map(([name, ok]) => (
              <li key={name} className={`chip ${ok ? "ok" : "bad"}`}>
                <span className="dot-sm" /> {name}
              </li>
            ))}
            <li className="chip">active: {health.active_provider}</li>
            {health.offline && <li className="chip warn">offline mode</li>}
          </>
        )}
      </ul>
    </header>
  );
}

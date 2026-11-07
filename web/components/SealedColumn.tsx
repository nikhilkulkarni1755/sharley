import { tileState } from "../lib/run";
import type { SealedTile } from "../lib/types";

function Lock() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="currentColor">
      <path d="M4 7V5a4 4 0 1 1 8 0v2h1v7H3V7h1zm2 0h4V5a2 2 0 1 0-4 0v2z" />
    </svg>
  );
}

/** Renders only index and family: sealed tests expose nothing else, whatever the payload carries. */
export default function SealedColumn({ tiles, results }: { tiles: SealedTile[]; results: Record<number, boolean> }) {
  return (
    <section aria-label="Sealed tests" className="panel">
      <h3>Sealed tests <span className="muted">locked, {tiles.length} hidden</span></h3>
      <ul className="tiles">
        {tiles.map((t) => {
          const state = tileState(results, t.index);
          return (
            <li key={t.index} data-testid="sealed-tile" data-state={state} aria-label={`Sealed test ${t.index}, ${t.family}, ${state}`}>
              <Lock />
              <b>{t.index}</b>
              <small>{t.family}</small>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

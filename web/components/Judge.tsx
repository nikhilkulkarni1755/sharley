"use client";

import { useState } from "react";
import { openRunEvents, startRun, STACK } from "../lib/api";
import type { Bank, Demo } from "../lib/types";
import ErrorNote from "./ErrorNote";
import ExampleList from "./ExampleList";
import SealedColumn from "./SealedColumn";
import SubmitPanel, { type Submission } from "./SubmitPanel";
import VerdictBanner from "./VerdictBanner";
import { useRun } from "./useRun";

export type Mode = "live" | "replay";

interface Props {
  mode: Mode;
  onMode: (mode: Mode) => void;
  liveBank: Bank | null;
  demo: Demo | null;
  loadError: string | null;
  onRetry: () => void;
}

export default function Judge({ mode, onMode, liveBank, demo, loadError, onRetry }: Props) {
  const run = useRun();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<string[]>([]);
  const [last, setLast] = useState<Submission | null>(null);
  const bank = mode === "live" ? liveBank : (demo?.bank ?? null);

  const submit = async (s: Submission) => {
    setLast(s);
    setSubmitError(null);
    setRejected([]);
    try {
      const started = await startRun({
        bank: bank!.key,
        implementer_model: s.model,
        implementer_family: s.family,
        files: s.files,
        stack: STACK,
      });
      setRejected(started.rejected_paths);
      run.stream((onEvent) => openRunEvents(started.run_id, onEvent));
    } catch (e) {
      setSubmitError((e as Error).message);
    }
  };

  return (
    <div className="stack">
      <div className="row between">
        <h2>Judge</h2>
        <div className="seg" role="group" aria-label="Data source">
          {(["replay", "live"] as const).map((m) => (
            <button key={m} aria-pressed={mode === m} onClick={() => onMode(m)}>
              {m === "replay" ? "Replay" : "Live"}
            </button>
          ))}
        </div>
      </div>

      {mode === "replay" && loadError && <ErrorNote message={loadError} onRetry={onRetry} />}
      {mode === "live" && !bank && <p className="muted">No test bank yet. Build a spec in Intake and press Generate tests, or switch to Replay.</p>}

      {bank && (
        <>
          {mode === "replay" ? (
            <div className="panel row between">
              <span className="muted">Precomputed run from the demo fixture ({demo?.meta.note}).</span>
              <button className="primary" disabled={run.running} onClick={() => run.play(demo!.events)}>
                Play replay
              </button>
            </div>
          ) : (
            <SubmitPanel busy={run.running} onSubmit={submit} />
          )}
          {submitError && <ErrorNote message={submitError} onRetry={last ? () => submit(last) : undefined} />}
          {run.state.error && <ErrorNote message={run.state.error} onRetry={mode === "live" && last ? () => submit(last) : undefined} />}
          {run.running && <p className="muted" role="status">Running sealed tests…</p>}
          {rejected.length > 0 && <p className="note warn">Ignored paths (not allowed): {rejected.join(", ")}</p>}
          {run.state.verdict && <VerdictBanner event={run.state.verdict} />}
          <div className="judge-grid">
            <ExampleList examples={bank.examples} results={run.state.examples} />
            <SealedColumn tiles={bank.sealed} results={run.state.sealed} />
          </div>
        </>
      )}
    </div>
  );
}

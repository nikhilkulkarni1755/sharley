"use client";

import { useEffect, useState } from "react";
import { getSamples } from "../lib/api";
import { loadFiles, PITCHES, runErrorText, saveFiles } from "../lib/playground";
import type { Sample } from "../lib/types";
import CodeEditor from "./CodeEditor";
import ErrorNote from "./ErrorNote";
import ExampleList from "./ExampleList";
import SealedColumn from "./SealedColumn";
import VerdictBanner from "./VerdictBanner";
import { useRun } from "./useRun";
import { useSubmission } from "./useSubmission";

function Workbench({ sample }: { sample: Sample }) {
  const run = useRun();
  const { bank } = sample;
  const { submit, error, rejected, last } = useSubmission(bank, run);
  const [files, setFiles] = useState(() => loadFiles(sample));
  const [model, setModel] = useState("judge-playground");
  const [family, setFamily] = useState("human");
  const [attempts, setAttempts] = useState(0);

  const edit = (path: string, value: string) => {
    const next = { ...files, [path]: value };
    setFiles(next);
    saveFiles(sample.name, next);
  };

  const go = (s = { model: model.trim(), family: family.trim(), files }) => {
    setAttempts((n) => n + 1);
    return submit(s);
  };

  const reset = () => {
    setFiles(sample.files);
    saveFiles(sample.name, sample.files);
  };

  const accepted = run.state.verdict?.verdict.status === "Accepted";
  const errorText = error ?? run.state.error;

  return (
    <div className="playground">
      <div className="stack">
        <details className="panel">
          <summary>Plain-English spec</summary>
          <p className="spec-text">{sample.spec}</p>
        </details>
        {!bank && <p className="note warn">This backend is not prepared on this server, so there are no tests to run yet.</p>}
        <div className="panel stack">
          {Object.entries(files).map(([path, content]) => (
            <CodeEditor key={path} path={path} value={content} onChange={(v) => edit(path, v)} />
          ))}
          <p className="muted">Edit the code and run again — the hidden tests never leave the server.</p>
          <div className="row">
            <label>
              Implementer model
              <input value={model} onChange={(e) => setModel(e.target.value)} maxLength={100} />
            </label>
            <label>
              Implementer family
              <input value={family} onChange={(e) => setFamily(e.target.value)} maxLength={50} />
            </label>
          </div>
          <div className="row">
            <button className="primary" disabled={!bank || run.running} onClick={() => go()}>
              Run sealed tests
            </button>
            <button onClick={reset}>Reset code</button>
            <span className="chip" aria-label="Attempts">Attempts: {attempts}</span>
          </div>
        </div>
      </div>

      <div className="stack">
        {errorText && <ErrorNote message={runErrorText(errorText)} onRetry={last ? () => go(last) : undefined} />}
        {run.running && <p className="muted" role="status">Running sealed tests…</p>}
        {rejected.length > 0 && <p className="note warn">Ignored paths (not allowed): {rejected.join(", ")}</p>}
        {run.state.verdict && (
          <div className={accepted ? "celebrate" : undefined}>
            <VerdictBanner event={run.state.verdict} />
            {accepted && <p className="cheer" role="status">All sealed tests pass — verified independently in {attempts} attempt{attempts === 1 ? "" : "s"}.</p>}
          </div>
        )}
        {bank && (
          <>
            <ExampleList examples={bank.examples} results={run.state.examples} />
            <SealedColumn tiles={bank.sealed} results={run.state.sealed} />
          </>
        )}
      </div>
    </div>
  );
}

export default function Playground() {
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState<Sample["name"]>("payments");

  const load = () => getSamples().then(setSamples, (e: Error) => setError(e.message));

  const retry = () => {
    setError(null);
    void load();
  };

  useEffect(() => {
    void load();
  }, []);

  const sample = samples?.find((s) => s.name === name) ?? samples?.[0];

  return (
    <div className="stack">
      <h2>Playground</h2>
      <p className="muted">Pick a backend, tweak its code and let the sealed tests judge it.</p>
      {error && <ErrorNote message={error} onRetry={retry} />}
      {!samples && !error && <p className="muted">Loading backends…</p>}
      {samples && (
        <div className="cards" role="group" aria-label="Backend">
          {samples.map((s) => (
            <button key={s.name} className="card" aria-pressed={sample?.name === s.name} onClick={() => setName(s.name)}>
              <strong>{s.title}</strong>
              <span>{PITCHES[s.name]}</span>
            </button>
          ))}
        </div>
      )}
      {sample && <Workbench key={sample.name} sample={sample} />}
    </div>
  );
}

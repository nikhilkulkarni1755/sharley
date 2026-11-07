"use client";

import { useEffect, useState } from "react";
import { getRepoSamples, openRunEvents, startRepoRun } from "../lib/api";
import { repoUrlError } from "../lib/repo";
import type { RepoSample } from "../lib/types";
import ErrorNote from "./ErrorNote";
import RepoAudit from "./RepoAudit";
import SealedColumn from "./SealedColumn";
import SourceChip from "./SourceChip";
import VerdictBanner from "./VerdictBanner";
import { useRun } from "./useRun";

export default function Repo() {
  const run = useRun();
  const [samples, setSamples] = useState<RepoSample[]>([]);
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const loadSamples = () => getRepoSamples().then(setSamples, (e: Error) => setError(e.message));

  useEffect(() => {
    void loadSamples();
  }, []);

  const go = async () => {
    const problem = repoUrlError(url);
    setInvalid(problem);
    if (problem) return;
    setError(null);
    try {
      const { run_id } = await startRepoRun(url.trim(), branch.trim() || undefined);
      setStarted(true);
      run.stream((onEvent) => openRunEvents(run_id, onEvent));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const errorText = error ?? run.state.error;
  const sealedTiles = Object.keys(run.state.sealed).map((i) => ({ index: Number(i), family: "sealed" }));

  return (
    <div className="stack">
      <h2>GitHub repo</h2>
      <p className="muted">Public GitHub repos only. Code runs in a network-less sandbox; nothing you paste here is stored beyond this run.</p>
      <SourceChip kind="prebuilt" />
      {samples.length > 0 && (
        <div className="cards" role="group" aria-label="Sample repos">
          {samples.map((s) => (
            <button key={s.name} className="card" onClick={() => setUrl(s.url)}>
              <strong>{s.title}</strong>
              <span>{s.pitch}</span>
            </button>
          ))}
        </div>
      )}
      <div className="panel stack">
        <div className="row">
          <label>
            Repo URL
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/name" maxLength={200} />
          </label>
          <label>
            Branch (optional)
            <input value={branch} onChange={(e) => setBranch(e.target.value)} maxLength={100} />
          </label>
        </div>
        {invalid && <p role="alert" className="note bad">{invalid}</p>}
        <div className="row">
          <button className="primary" disabled={run.running} onClick={go}>
            Verify repo
          </button>
        </div>
      </div>
      {started && <SourceChip kind="live" />}
      {errorText && <ErrorNote message={errorText} onRetry={go} />}
      {started && <RepoAudit state={run.state} running={run.running} />}
      {run.state.verdict && (
        <>
          <VerdictBanner event={run.state.verdict} sealed={run.state.sealed} />
          <SealedColumn tiles={sealedTiles} results={run.state.sealed} />
        </>
      )}
    </div>
  );
}

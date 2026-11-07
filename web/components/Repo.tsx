"use client";

import { useEffect, useState } from "react";
import { getRepoSamples, openRunEvents, startRepoRun } from "../lib/api";
import { formatElapsed } from "../lib/pipeline";
import { repoUrlError } from "../lib/repo";
import { isFinal } from "../lib/run";
import type { RepoSample } from "../lib/types";
import ErrorNote from "./ErrorNote";
import RepoAudit from "./RepoAudit";
import SealedColumn from "./SealedColumn";
import SourceChip from "./SourceChip";
import SummaryCard from "./SummaryCard";
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
  const [elapsed, setElapsed] = useState<number | null>(null);

  const loadSamples = () => getRepoSamples().then(setSamples, (e: Error) => setError(e.message));

  useEffect(() => {
    void loadSamples();
  }, []);

  const go = async () => {
    const problem = repoUrlError(url);
    setInvalid(problem);
    if (problem) return;
    setError(null);
    setElapsed(null);
    const t0 = Date.now();
    try {
      const { run_id } = await startRepoRun(url.trim(), branch.trim() || undefined);
      setStarted(true);
      run.stream((onEvent) =>
        openRunEvents(run_id, (e) => {
          if (isFinal(e)) setElapsed(Date.now() - t0);
          onEvent(e);
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const { report } = run.state;
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
      {elapsed !== null && (report || run.state.verdict) && (
        <SummaryCard>
          <h3>
            {report
              ? report.boot_ok
                ? `All done in ${formatElapsed(elapsed)}: ${report.passed} of ${report.total} generated tests passed, ${report.failed} failures`
                : `Finished in ${formatElapsed(elapsed)}: could not start this repo`
              : `Finished in ${formatElapsed(elapsed)}: ${run.state.verdict!.verdict.status}`}
          </h3>
        </SummaryCard>
      )}
      {run.state.verdict && (
        <>
          <VerdictBanner event={run.state.verdict} sealed={run.state.sealed} />
          <SealedColumn tiles={sealedTiles} results={run.state.sealed} />
        </>
      )}
    </div>
  );
}

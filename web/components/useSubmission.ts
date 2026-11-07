import { useState } from "react";
import { openRunEvents, startRun, STACK } from "../lib/api";
import type { Bank } from "../lib/types";
import type { Submission } from "./SubmitPanel";
import type { useRun } from "./useRun";

/** Starts a run for `bank` and streams its events into `run`; remembers the last submission for retry. */
export function useSubmission(bank: Bank | null, run: ReturnType<typeof useRun>) {
  const [error, setError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<string[]>([]);
  const [last, setLast] = useState<Submission | null>(null);

  const submit = async (s: Submission) => {
    setLast(s);
    setError(null);
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
      setError((e as Error).message);
    }
  };

  return { submit, error, rejected, last };
}

import type { RunEvent } from "./types";

type EventOf<T extends RunEvent["type"]> = Extract<RunEvent, { type: T }>;

export interface RunState {
  examples: Record<string, boolean>;
  sealed: Record<number, boolean>;
  verdict: EventOf<"verdict"> | null;
  stage: EventOf<"stage"> | null;
  surface: EventOf<"surface"> | null;
  findings: EventOf<"finding">[];
  report: EventOf<"report"> | null;
  error: string | null;
}

export const emptyRun: RunState = { examples: {}, sealed: {}, verdict: null, stage: null, surface: null, findings: [], report: null, error: null };

/** The events after which the stream is over. */
export const isFinal = (e: RunEvent): boolean => e.type === "verdict" || e.type === "report" || e.type === "error";

/** Folds one SSE event into the run state; absent keys mean the test has not reported yet. */
export function applyEvent(state: RunState, event: RunEvent): RunState {
  switch (event.type) {
    case "example":
      return { ...state, examples: { ...state.examples, [event.id]: event.passed } };
    case "sealed":
      return { ...state, sealed: { ...state.sealed, [event.index]: event.passed } };
    case "verdict":
      return { ...state, verdict: event };
    case "stage":
      return { ...state, stage: event };
    case "surface":
      return { ...state, surface: event };
    case "finding":
      return { ...state, findings: [...state.findings, event] };
    case "report":
      return { ...state, report: event };
    case "error":
      return { ...state, error: event.detail };
  }
}

export type TileState = "pending" | "passed" | "failed";

export function tileState(results: Record<string | number, boolean>, key: string | number): TileState {
  return key in results ? (results[key] ? "passed" : "failed") : "pending";
}

/** Releases queued events one at a time so bursts still animate. */
export function createStagger<T>(handler: (item: T) => void, delayMs: number) {
  const queue: T[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;
  const drain = () => {
    const next = queue.shift();
    timer = null;
    if (next === undefined) return;
    handler(next);
    timer = setTimeout(drain, delayMs);
  };
  return {
    push(item: T) {
      queue.push(item);
      if (!timer) drain();
    },
    clear() {
      queue.length = 0;
      if (timer) clearTimeout(timer);
      timer = null;
    },
  };
}

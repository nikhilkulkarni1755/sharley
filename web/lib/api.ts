import { isSpendCap } from "./pipeline";
import { isFinal } from "./run";
import type { Bank, Demo, Health, RepoSample, RunEvent, RunRequest, Sample, Spec } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const STACK = "docker-api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly retryable: boolean,
    readonly detail?: unknown,
  ) {
    super(message);
  }
}

export function friendlyMessage(status: number, detail: unknown): string {
  const text = typeof detail === "string" ? detail : "the request was rejected";
  if (status === 503 && isSpendCap(detail)) return text;
  if (status === 503) return `Provider unavailable, retry in a moment. (${text})`;
  if (status === 403) return "Live repo audit is disabled on this public link. Try a sample repo.";
  if (status === 429) return "Sharley is busy or rate limited right now. Please retry in a minute.";
  if (status === 422) return `Invalid input: ${text}`;
  if (status === 413) return "That payload is too large.";
  if (status === 404) return `Not found: ${text}`;
  return `Request failed (${status}): ${text}`;
}

async function request(path: string, body?: unknown): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is it running?`, true);
  }
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new ApiError(friendlyMessage(res.status, payload.detail), res.status >= 500 && !isSpendCap(payload.detail), payload.detail);
  }
  return res;
}

const call = async <T>(path: string, body?: unknown): Promise<T> => (await request(path, body)).json();

export const getHealth = () => call<Health>("/api/health");
export const getSamples = () => call<Sample[]>("/api/samples");
export const getDemo = () => call<Demo>("/api/demo");
export const createSpec = (text: string) => call<Spec>("/api/specs", { text });
export const createSpecFromImage = (image_b64: string) => call<Spec>("/api/specs/image", { image_b64 });
export const createBank = (spec_hash: string, allow_partial = false) =>
  call<Bank>("/api/banks", { spec_hash, stack: STACK, seed: 0, allow_partial });
export const downloadProject = async (bankKey: string, image_b64?: string): Promise<Blob> =>
  (await request(`/api/banks/${encodeURIComponent(bankKey)}/project`, { image_b64 })).blob();
export const startRun = (req: RunRequest) =>
  call<{ run_id: string; rejected_paths: string[] }>("/api/runs", req);

export const getRepoSamples = () => call<RepoSample[]>("/api/repos/samples");
export const startRepoRun = (url: string, branch?: string) =>
  call<{ run_id: string; mode: "sealed" | "audit" }>("/api/repos", { url, branch });

const NAMED_EVENTS = ["example", "sealed", "verdict", "stage", "surface", "finding", "report"];

/** Streams run events; the server names each SSE event, so listen per type as well as on unnamed messages. */
export function openRunEvents(runId: string, onEvent: (e: RunEvent) => void): () => void {
  const source = new EventSource(`${API_URL}/api/runs/${runId}/events`);
  const handle = (m: MessageEvent) => {
    const event: RunEvent = JSON.parse(m.data);
    onEvent(event);
    if (isFinal(event)) source.close();
  };
  source.onmessage = handle;
  for (const type of NAMED_EVENTS) {
    source.addEventListener(type, (m) => handle(m as MessageEvent));
  }
  source.addEventListener("error", (m) => {
    if (m instanceof MessageEvent) return handle(m);
    source.close();
    onEvent({ type: "error", detail: "Lost connection to the event stream, retry." });
  });
  return () => source.close();
}

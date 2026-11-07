import type { Status, Verdict } from "./types";

export type Tone = "ok" | "bad" | "warn";

const TONES: Record<Status, Tone> = {
  Accepted: "ok",
  "Wrong Answer": "bad",
  "Runtime Error": "bad",
  "Time Limit Exceeded": "warn",
  "Build Failed": "warn",
  "Rejected: tests tampered": "bad",
};

export const verdictTone = (status: Status): Tone => TONES[status];

export const verdictHeadline = (status: Status, summary: string): string => summary || status;

export const examplesLine = (v: Verdict): string => `Visible examples: ${v.example_passed}/${v.example_total} passed`;

/** Sealed passes come from the streamed events; with none streamed, only an Accepted verdict implies them. */
export const sealedLine = (v: Verdict, sealed: Record<number, boolean>): string => {
  const results = Object.values(sealed);
  const passed = results.length ? results.filter(Boolean).length : v.status === "Accepted" ? v.total_sealed : 0;
  return `Hidden sealed tests: ${passed}/${v.total_sealed} passed`;
};

/** Examples all green yet a sealed test red: the case judges find confusing. */
export const hidesFailures = (v: Verdict, sealed: Record<number, boolean>): boolean =>
  v.example_passed === v.example_total && Object.values(sealed).some((ok) => !ok);

export const isIndependent = (v: Verdict): boolean => v.implementer.family !== v.verifier.family;

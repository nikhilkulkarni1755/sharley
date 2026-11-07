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

export const examplesLine = (v: Verdict): string => `${v.example_passed}/${v.example_total} examples passed`;

export const isIndependent = (v: Verdict): boolean => v.implementer.family !== v.verifier.family;

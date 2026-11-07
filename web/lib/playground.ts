import type { Sample } from "./types";

export const PITCHES: Record<Sample["name"], string> = {
  payments: "Payments for users AND AI agents — hides a logic bug and a security hole",
  electricity: "Electricity billing — 3 of 12 houses silently get free power",
};

const storageKey = (name: string) => `sharley:playground:${name}`;

/** A judge's edits survive a refresh, per backend. Storage can be blocked, so fall back to the shipped code. */
export function loadFiles(sample: Sample): Record<string, string> {
  try {
    const saved: Record<string, unknown> | null = JSON.parse(sessionStorage.getItem(storageKey(sample.name)) ?? "null");
    if (saved && Object.keys(sample.files).every((path) => typeof saved[path] === "string")) {
      return saved as Record<string, string>;
    }
  } catch {
    // fall through to the shipped code
  }
  return sample.files;
}

export function saveFiles(name: string, files: Record<string, string>) {
  try {
    sessionStorage.setItem(storageKey(name), JSON.stringify(files));
  } catch {
    // editing still works without persistence
  }
}

/** The API says "must be different model families"; tell the judge what to do about it. */
export const runErrorText = (message: string): string =>
  /famil/i.test(message) ? "Pick a different family: the implementer must not share a family with the verifier." : message;

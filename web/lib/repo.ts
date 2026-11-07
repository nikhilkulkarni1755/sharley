import type { RepoStage } from "./types";

const REPO_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/;

export const repoUrlError = (url: string): string | null =>
  REPO_URL.test(url.trim()) ? null : "Enter a public repo URL like https://github.com/owner/name";

export const STAGES: { id: RepoStage; label: string }[] = [
  { id: "cloning", label: "Cloning" },
  { id: "analyzing", label: "Analyzing" },
  { id: "writing_tests", label: "Writing tests" },
  { id: "running_tests", label: "Running tests" },
];

export type StepState = "done" | "active" | "pending";

/** Stages before the current one are done; once the run is over (`finished`) all are. */
export const stepState = (index: number, current: RepoStage | null, finished: boolean): StepState => {
  const at = STAGES.findIndex((s) => s.id === current);
  return finished || index < at ? "done" : index === at ? "active" : "pending";
};

export type Category = "functional" | "security" | "deployment" | "data";

export interface Evidence {
  kind: "observed" | "inferred";
  source_span: string | null;
  assumption_id: string | null;
}

export interface Requirement {
  id: string;
  text: string;
  category: Category;
  evidence: Evidence;
}

export interface Spec {
  stack: string | null;
  requirements: Requirement[];
  assumptions: Record<string, string>;
  ignored: { span: string; reason: string }[];
  coverage_pct: number;
  spec_hash: string;
  active_provider?: string;
}

export interface ModelRef {
  provider?: string;
  model: string;
  family: string;
}

export interface ExampleTest {
  id: string;
  name: string;
  family: string;
  requirement_ids: string[];
  file: string;
  code: string;
}

export interface SealedTile {
  index: number;
  family: string;
}

export interface Bank {
  key: string;
  spec_hash: string;
  seed: number;
  author: ModelRef | null;
  examples: ExampleTest[];
  sealed: SealedTile[];
}

export type Status =
  | "Accepted"
  | "Wrong Answer"
  | "Runtime Error"
  | "Time Limit Exceeded"
  | "Build Failed"
  | "Rejected: tests tampered";

export interface Verdict {
  status: Status;
  failed_test_index: number | null;
  total_sealed: number;
  requirement_ids: string[];
  hint: string;
  example_passed: number;
  example_total: number;
  implementer: ModelRef;
  verifier: ModelRef;
  seed: number;
  spec_hash: string;
}

export type RunEvent =
  | { type: "example"; id: string; name: string; passed: boolean }
  | { type: "sealed"; index: number; passed: boolean }
  | { type: "verdict"; verdict: Verdict; summary: string; rejected_paths: string[] }
  | { type: "error"; detail: string };

export interface Mutant {
  id: string;
  operator: string;
  category: "functional" | "security";
  split: "train" | "heldout";
  killed: boolean | null;
}

export interface Scores {
  heldout_mutation_score: number;
  false_failure_rate: number;
  security_kill_rate: number;
  production_worthy: number;
}

export interface SkillVersion {
  version: number;
  parent: number | null;
  rules: string[];
  diff: string;
  scores: Scores | null;
  decision: "baseline" | "adopted" | "rolled_back";
  reason: string;
}

export interface Demo {
  meta: { source: string; generated_at: string; note: string };
  spec: Spec;
  bank: Bank;
  events: RunEvent[];
  eval: { mutants: Mutant[]; reference: { tests: number; failed: number }; scores: Scores };
  timeline: SkillVersion[];
}

export interface Health {
  status: string;
  offline: boolean;
  providers: Record<string, boolean>;
  active_provider: string;
}

export interface RunRequest {
  bank: string;
  implementer_model: string;
  implementer_family: string;
  files: Record<string, string>;
  stack: string;
}

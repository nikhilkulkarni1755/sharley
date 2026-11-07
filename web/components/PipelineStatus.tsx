import { formatElapsed, STEP_LABELS, type Step } from "../lib/pipeline";

export default function PipelineStatus({ steps }: { steps: Step[] }) {
  return (
    <ol className="stepper pipeline" aria-label="Pipeline">
      {steps.map((s, i) => (
        <li key={STEP_LABELS[i]} data-state={s.state}>
          {STEP_LABELS[i]}
          {s.state === "done" && s.ms !== undefined && <small> {formatElapsed(s.ms)}</small>}
          {s.state === "failed" && <small> {s.reason}</small>}
        </li>
      ))}
    </ol>
  );
}

import type { Demo } from "../lib/types";

const KINDS = {
  live: { label: "LIVE", text: "Answered by the API just now." },
  recorded: { label: "RECORDED", text: "Replayed from a prebuilt fixture, not a fresh run." },
  prebuilt: {
    label: "PRE-BUILT",
    text: "Judging runs for real in the sandbox; the hidden tests were generated ahead of time, so no model is called.",
  },
} as const;

/** Says where a panel's data came from; `meta` adds the fixture's own provenance for recorded data. */
export default function SourceChip({ kind, meta }: { kind: keyof typeof KINDS; meta?: Demo["meta"] }) {
  const { label, text } = KINDS[kind];
  return (
    <div className="source">
      <span className={`chip src ${kind}`}>{label}</span>
      <span className="muted">{text}</span>
      {meta && (
        <>
          <span className="muted">Generated {meta.generated_at}.</span>
          <details>
            <summary>What&apos;s recorded?</summary>
            <p>{meta.note}</p>
            <p>{meta.source}</p>
          </details>
        </>
      )}
    </div>
  );
}

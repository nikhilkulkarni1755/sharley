"use client";

import type { KeyboardEvent } from "react";

export const TABS = [
  { id: "intake", label: "Intake" },
  { id: "judge", label: "Judge" },
  { id: "eval", label: "Eval" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export default function Tabs({ active, onChange }: { active: TabId; onChange: (id: TabId) => void }) {
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
    const next =
      e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : e.key in step ? (index + step[e.key] + TABS.length) % TABS.length : null;
    if (next === null) return;
    e.preventDefault();
    onChange(TABS[next].id);
    document.getElementById(`tab-${TABS[next].id}`)?.focus();
  };

  return (
    <div role="tablist" aria-label="Board" className="tabs">
      {TABS.map((t, i) => (
        <button
          key={t.id}
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={active === t.id}
          aria-controls={`panel-${t.id}`}
          tabIndex={active === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKeyDown(e, i)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

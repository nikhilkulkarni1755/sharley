"use client";

import { useRef, type KeyboardEvent } from "react";

const INDENT = "    ";

/** A plain textarea with a line-number gutter; Tab indents instead of leaving the field. */
export default function CodeEditor({ path, value, onChange }: { path: string; value: string; onChange: (value: string) => void }) {
  const gutter = useRef<HTMLPreElement>(null);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Tab" || e.shiftKey) return;
    e.preventDefault();
    const t = e.currentTarget;
    t.setRangeText(INDENT, t.selectionStart, t.selectionEnd, "end");
    onChange(t.value);
  };

  return (
    <div className="editor">
      <div className="editor-path mono">{path}</div>
      <div className="editor-body">
        <pre ref={gutter} className="gutter" aria-hidden="true">
          {value.split("\n").map((_, i) => i + 1).join("\n")}
        </pre>
        <textarea
          aria-label={path}
          spellCheck={false}
          wrap="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onScroll={(e) => {
            gutter.current!.scrollTop = e.currentTarget.scrollTop;
          }}
        />
      </div>
    </div>
  );
}

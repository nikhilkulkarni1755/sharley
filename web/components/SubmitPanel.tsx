"use client";

import { useState } from "react";
import { parseFiles } from "../lib/files";

export interface Submission {
  model: string;
  family: string;
  files: Record<string, string>;
}

const STARTER = '{\n  "app.py": "# your implementation"\n}';

export default function SubmitPanel({ busy, onSubmit }: { busy: boolean; onSubmit: (s: Submission) => void }) {
  const [model, setModel] = useState("");
  const [family, setFamily] = useState("");
  const [filesText, setFilesText] = useState(STARTER);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const parsed = parseFiles(filesText);
    if ("error" in parsed) return setError(parsed.error);
    setError(null);
    onSubmit({ model: model.trim(), family: family.trim(), files: parsed.files });
  };

  return (
    <form
      className="panel stack"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <h3>Submit implementation</h3>
      <div className="row">
        <label>
          Implementer model
          <input value={model} onChange={(e) => setModel(e.target.value)} required maxLength={100} placeholder="e.g. gpt-5" />
        </label>
        <label>
          Implementer family
          <input value={family} onChange={(e) => setFamily(e.target.value)} required maxLength={50} placeholder="e.g. openai" />
        </label>
      </div>
      <label>
        Files (JSON: path to content)
        <textarea className="code" rows={8} spellCheck={false} value={filesText} onChange={(e) => setFilesText(e.target.value)} />
      </label>
      {error && <p className="field-error" role="alert">{error}</p>}
      <button className="primary" type="submit" disabled={busy}>
        Submit implementation
      </button>
    </form>
  );
}

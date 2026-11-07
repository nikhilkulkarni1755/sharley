"use client";

import { useState, type DragEvent } from "react";
import { createBank, createSpec, createSpecFromImage } from "../lib/api";
import { classifyFile, readDataUri, stripDataUri } from "../lib/files";
import type { Bank, Spec } from "../lib/types";
import ErrorNote from "./ErrorNote";
import SourceChip from "./SourceChip";
import SpecView from "./SpecView";
import TraceImage from "./TraceImage";
import Webcam from "./Webcam";

const REJECTIONS = {
  unsupported: "Drop a text file or a PNG/JPEG image.",
  "too-large": "That image is too large (8 MB max).",
} as const;

export default function Intake({ onBank }: { onBank: (bank: Bank) => void }) {
  const [text, setText] = useState("");
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [webcam, setWebcam] = useState(false);
  const [spec, setSpec] = useState<Spec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<(() => void) | null>(null);

  const run = async (task: () => Promise<Spec>, again: () => void) => {
    setBusy(true);
    setError(null);
    try {
      setSpec(await task());
      setRetry(null);
    } catch (e) {
      setError((e as Error).message);
      setRetry(() => again);
    } finally {
      setBusy(false);
      setImageSrc(null);
    }
  };

  const submitText = (value: string) => run(() => createSpec(value), () => submitText(value));

  const submitImage = (dataUri: string) => {
    setImageSrc(dataUri);
    return run(() => createSpecFromImage(stripDataUri(dataUri)), () => submitImage(dataUri));
  };

  const ingest = async (file: File) => {
    const kind = classifyFile(file);
    if (kind === "unsupported" || kind === "too-large") return setError(REJECTIONS[kind]);
    if (kind === "image") return submitImage(await readDataUri(file));
    const content = await file.text();
    setText(content);
    return submitText(content);
  };

  const closeWebcam = (reason?: string) => {
    setWebcam(false);
    if (reason) setError(reason);
  };

  const captured = (png: File) => {
    setWebcam(false);
    void ingest(png);
  };

  const useSample = async () => {
    try {
      const blob = await (await fetch("/sample-sketch.png")).blob();
      await ingest(new File([blob], "sample-sketch.png", { type: "image/png" }));
    } catch {
      setError("Could not load the sample sketch.");
    }
  };

  const onDrop =(e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) void ingest(file);
  };

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      onBank(await createBank(spec!.spec_hash));
    } catch (e) {
      setError((e as Error).message);
      setRetry(() => generate);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {imageSrc ? (
        <TraceImage src={imageSrc} />
      ) : (
        <div
          className={`drop ${dragging ? "over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <label htmlFor="spec-text">Paste a spec, or drop a text file / PNG / JPEG here</label>
          <textarea
            id="spec-text"
            rows={7}
            value={text}
            placeholder="Users can sign up and log in. Each user can create private notes..."
            onChange={(e) => setText(e.target.value)}
          />
          <div className="row">
            <button className="primary" disabled={busy || !text.trim()} onClick={() => submitText(text)}>
              Build spec
            </button>
            <label className="button">
              Choose file
              <input
                type="file"
                accept=".txt,.md,.markdown,text/*,image/png,image/jpeg"
                onChange={(e) => e.target.files?.[0] && void ingest(e.target.files[0])}
              />
            </label>
          </div>
          <div className="row">
            <label className="button">
              Take a photo
              <input type="file" accept="image/*" capture="environment" onChange={(e) => e.target.files?.[0] && void ingest(e.target.files[0])} />
            </label>
            <button onClick={() => setWebcam(true)} disabled={webcam}>Use webcam</button>
            <button onClick={useSample}>Try the sample sketch</button>
          </div>
        </div>
      )}
      {webcam && !imageSrc && <Webcam onCapture={captured} onClose={closeWebcam} />}
      {busy &&!imageSrc && <p className="muted">Working…</p>}
      {error && <ErrorNote message={error} onRetry={retry ?? undefined} />}
      {spec && <SourceChip kind="live" />}
      {spec && <SpecView spec={spec} busy={busy} onGenerate={generate} />}
    </div>
  );
}

"use client";

import { useState, type DragEvent } from "react";
import { ApiError, createBank, createSpec, createSpecFromImage } from "../lib/api";
import { classifyFile, readDataUri, stripDataUri } from "../lib/files";
import { idleSteps, summaryText, totalMs, untestedIds, withStep, type Step } from "../lib/pipeline";
import type { Bank, Spec } from "../lib/types";
import ErrorNote from "./ErrorNote";
import PipelineStatus from "./PipelineStatus";
import SourceChip from "./SourceChip";
import SpecView from "./SpecView";
import SummaryCard from "./SummaryCard";
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
  const [steps, setSteps] = useState<Step[]>(idleSteps);
  const [bank, setBank] = useState<Bank | null>(null);
  const [missing, setMissing] = useState<string[] | null>(null);

  const setStep = (index: number, step: Step) => setSteps((s) => withStep(s, index, step));

  const run = async (task: () => Promise<Spec>, again: () => void) => {
    const started = Date.now();
    setBusy(true);
    setError(null);
    setBank(null);
    setMissing(null);
    setSteps(withStep(withStep(idleSteps(), 0, { state: "done", ms: 0 }), 1, { state: "running" }));
    try {
      setSpec(await task());
      setStep(1, { state: "done", ms: Date.now() - started });
      setRetry(null);
    } catch (e) {
      setError((e as Error).message);
      setStep(1, { state: "failed", reason: (e as Error).message });
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

  const generate = async (allowPartial = false) => {
    const started = Date.now();
    setBusy(true);
    setError(null);
    setStep(2, { state: "running" });
    try {
      setBank(await createBank(spec!.spec_hash, allowPartial));
      setStep(2, { state: "done", ms: Date.now() - started });
      setStep(3, { state: "done" });
    } catch (e) {
      const ids = untestedIds((e as ApiError).detail);
      setStep(2, { state: "failed", reason: ids ? `${ids.length} requirements without tests` : (e as Error).message });
      if (ids) {
        setMissing(ids);
      } else {
        setError((e as Error).message);
        setRetry((e as ApiError).retryable ? () => () => generate() : null);
      }
    } finally {
      setBusy(false);
    }
  };

  const startOver = () => {
    setText("");
    setSpec(null);
    setBank(null);
    setMissing(null);
    setError(null);
    setSteps(idleSteps());
  };

  return (
    <div className="stack">
      <PipelineStatus steps={steps} />
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
      {missing && !bank && (
        <div role="alert" className="note warn">
          <span>{missing.length} requirements could not be tested ({missing.join(", ")}).</span>
          <span className="row">
            <button className="primary" disabled={busy} onClick={() => generate(true)}>Continue with a partial bank</button>
            <button onClick={() => setMissing(null)}>Cancel</button>
          </span>
        </div>
      )}
      {spec && bank && (
        <SummaryCard
          actions={
            <>
              <button className="primary" onClick={() => onBank(bank)}>Open in Judge</button>
              <button onClick={startOver}>Start over</button>
            </>
          }
        >
          <h3>{summaryText(spec, bank, totalMs(steps))}</h3>
          {missing && <p className="warn-text">{missing.length} requirements untested</p>}
          <p className="muted">
            Spec model: {spec.active_provider ?? "unknown"}
            {bank.author && ` · tests written by ${[bank.author.provider, bank.author.model].filter(Boolean).join(" ")}`}
          </p>
        </SummaryCard>
      )}
      {spec && <SpecView spec={spec} busy={busy} onGenerate={() => generate()} />}
    </div>
  );
}

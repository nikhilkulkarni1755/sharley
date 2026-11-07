import { afterEach, describe, expect, it, vi } from "vitest";
import { applyEvent, createStagger, emptyRun, tileState } from "../lib/run";
import type { RunEvent, Verdict } from "../lib/types";

const verdict = { status: "Accepted" } as Verdict;

describe("applyEvent", () => {
  it("records example and sealed results without mutating the previous state", () => {
    const a = applyEvent(emptyRun, { type: "example", id: "ex1", name: "n", passed: true });
    const b = applyEvent(a, { type: "sealed", index: 3, passed: false });
    expect(b.examples).toEqual({ ex1: true });
    expect(b.sealed).toEqual({ 3: false });
    expect(emptyRun.sealed).toEqual({});
  });

  it("keeps the verdict and error", () => {
    const v = applyEvent(emptyRun, { type: "verdict", verdict, summary: "Accepted", rejected_paths: [] });
    expect(v.verdict?.summary).toBe("Accepted");
    expect(applyEvent(v, { type: "error", detail: "boom" }).error).toBe("boom");
  });
});

describe("tileState", () => {
  it("is pending until a result arrives", () => {
    expect(tileState({}, 1)).toBe("pending");
    expect(tileState({ 1: true }, 1)).toBe("passed");
    expect(tileState({ 1: false }, 1)).toBe("failed");
  });
});

describe("createStagger", () => {
  afterEach(() => vi.useRealTimers());

  it("releases a burst one item per tick, in order", () => {
    vi.useFakeTimers();
    const seen: RunEvent[] = [];
    const s = createStagger<RunEvent>((e) => seen.push(e), 10);
    s.push({ type: "sealed", index: 1, passed: true });
    s.push({ type: "sealed", index: 2, passed: true });
    s.push({ type: "sealed", index: 3, passed: false });
    expect(seen).toHaveLength(1);
    vi.advanceTimersByTime(10);
    expect(seen).toHaveLength(2);
    vi.advanceTimersByTime(10);
    expect(seen.map((e) => (e as { index: number }).index)).toEqual([1, 2, 3]);
  });

  it("clear drops pending items", () => {
    vi.useFakeTimers();
    const seen: number[] = [];
    const s = createStagger<number>((n) => seen.push(n), 10);
    s.push(1);
    s.push(2);
    s.clear();
    vi.advanceTimersByTime(100);
    expect(seen).toEqual([1]);
    s.push(3);
    expect(seen).toEqual([1, 3]);
  });
});

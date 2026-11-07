import { beforeEach, describe, expect, it } from "vitest";
import { loadFiles, runErrorText, saveFiles } from "../lib/playground";
import type { Sample } from "../lib/types";

const sample: Sample = { name: "payments", title: "P", spec: "s", files: { "app/main.py": "a", "app/db.py": "b" }, bank: null };

describe("playground files", () => {
  beforeEach(() => sessionStorage.clear());

  it("falls back to the shipped code, then returns saved edits", () => {
    expect(loadFiles(sample)).toEqual(sample.files);
    saveFiles("payments", { "app/main.py": "edited", "app/db.py": "b" });
    expect(loadFiles(sample)["app/main.py"]).toBe("edited");
  });

  it("ignores corrupt or mismatched saved edits", () => {
    sessionStorage.setItem("sharley:playground:payments", "{nope");
    expect(loadFiles(sample)).toEqual(sample.files);
    saveFiles("payments", { "app/main.py": "only one file" });
    expect(loadFiles(sample)).toEqual(sample.files);
  });

  it("survives blocked storage", () => {
    const blocked = Object.getOwnPropertyDescriptor(window, "sessionStorage")!;
    Object.defineProperty(window, "sessionStorage", { get: () => { throw new Error("blocked"); }, configurable: true });
    try {
      expect(loadFiles(sample)).toEqual(sample.files);
      expect(() => saveFiles("payments", sample.files)).not.toThrow();
    } finally {
      Object.defineProperty(window, "sessionStorage", blocked);
    }
  });
});

describe("runErrorText", () => {
  it("turns the same-family rejection into advice and passes other messages through", () => {
    expect(runErrorText("Invalid input: implementer and verifier must be different model families")).toMatch(/^Pick a different family/);
    expect(runErrorText("Provider unavailable, retry in a moment.")).toBe("Provider unavailable, retry in a moment.");
  });
});

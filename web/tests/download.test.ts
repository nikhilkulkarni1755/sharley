import { afterEach, describe, expect, it, vi } from "vitest";
import { projectFilename, saveBlob } from "../lib/download";
import type { Bank } from "../lib/types";

afterEach(() => vi.restoreAllMocks());

describe("projectFilename", () => {
  it("uses the first 8 chars of the spec hash", () => {
    expect(projectFilename({ spec_hash: "b41e07d95ac3c216e8f0" } as Bank)).toBe("sharley-project-b41e07d9.zip");
  });
});

describe("saveBlob", () => {
  it("clicks a download link with the filename, then revokes the object URL", () => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe("a.zip");
      expect(this.href).toBe("blob:x");
    });
    saveBlob(new Blob(["PK"]), "a.zip");
    expect(click).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:x");
  });
});

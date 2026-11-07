import { describe, expect, it } from "vitest";
import { repoUrlError, stepState } from "../lib/repo";

describe("repoUrlError", () => {
  it("accepts public GitHub repo URLs", () => {
    for (const url of ["https://github.com/acme/notes", "https://github.com/acme/notes/", " https://github.com/a.b/c_d-e "]) {
      expect(repoUrlError(url)).toBeNull();
    }
  });

  it("rejects everything else", () => {
    for (const url of ["", "github.com/acme/notes", "http://github.com/acme/notes", "https://gitlab.com/acme/notes", "https://github.com/acme", "https://github.com/acme/notes/tree/main", "https://github.com.evil.io/a/b"]) {
      expect(repoUrlError(url)).not.toBeNull();
    }
  });
});

describe("stepState", () => {
  it("marks earlier stages done, the current one active and later ones pending", () => {
    expect([0, 1, 2, 3].map((i) => stepState(i, "writing_tests", false))).toEqual(["done", "done", "active", "pending"]);
  });

  it("is all pending before the first stage and all done when finished", () => {
    expect(stepState(0, null, false)).toBe("pending");
    expect(stepState(3, "cloning", true)).toBe("done");
  });
});

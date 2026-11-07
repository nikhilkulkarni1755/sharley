import { describe, expect, it } from "vitest";
import { classifyFile, MAX_IMAGE_BYTES, parseFiles, stripDataUri } from "../lib/files";

describe("parseFiles", () => {
  it("accepts a path to content object", () => {
    expect(parseFiles('{"app.py": "print(1)"}')).toEqual({ files: { "app.py": "print(1)" } });
  });

  it.each([["not json"], ["[]"], ["{}"], ["null"], ['{"a": 1}']])("rejects %s", (text) => {
    expect(parseFiles(text)).toHaveProperty("error");
  });
});

describe("classifyFile", () => {
  const f = (name: string, type: string, size = 10) => ({ name, type, size });

  it("recognises images, text and the rest", () => {
    expect(classifyFile(f("a.png", "image/png"))).toBe("image");
    expect(classifyFile(f("a.jpg", "image/jpeg"))).toBe("image");
    expect(classifyFile(f("a.txt", "text/plain"))).toBe("text");
    expect(classifyFile(f("spec.md", ""))).toBe("text");
    expect(classifyFile(f("a.gif", "image/gif"))).toBe("unsupported");
    expect(classifyFile(f("a.exe", "application/octet-stream"))).toBe("unsupported");
  });

  it("flags oversized images", () => {
    expect(classifyFile(f("a.png", "image/png", MAX_IMAGE_BYTES + 1))).toBe("too-large");
  });
});

describe("stripDataUri", () => {
  it("removes the data URI prefix the API rejects", () => {
    expect(stripDataUri("data:image/png;base64,QUJD")).toBe("QUJD");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createSpec, downloadProject, friendlyMessage } from "../lib/api";

afterEach(() => vi.unstubAllGlobals());

const respond = (status: number, body: unknown) =>
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body }));

describe("friendlyMessage", () => {
  it("explains provider outages as retryable", () => {
    expect(friendlyMessage(503, "intake failed")).toMatch(/provider unavailable, retry/i);
  });

  it("surfaces validation details and tolerates non-string details", () => {
    expect(friendlyMessage(422, "bad base64")).toContain("bad base64");
    expect(friendlyMessage(422, [{ loc: ["body"] }])).toContain("rejected");
  });
});

describe("call", () => {
  it("posts JSON and returns the body", async () => {
    respond(200, { spec_hash: "h" });
    await expect(createSpec("hello")).resolves.toEqual({ spec_hash: "h" });
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"text":"hello"}');
  });

  it("maps 503 to a retryable ApiError and 422 to a non-retryable one", async () => {
    respond(503, { detail: "down" });
    await expect(createSpec("x")).rejects.toMatchObject({ retryable: true, message: expect.stringMatching(/provider unavailable/i) });
    respond(422, { detail: "nope" });
    await expect(createSpec("x")).rejects.toMatchObject({ retryable: false });
  });

  it("reports an unreachable API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    const err = await createSpec("x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/cannot reach the API/i);
  });
});

describe("downloadProject", () => {
  it("posts the encoded bank key and returns the zip blob", async () => {
    const blob = new Blob(["PK"]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => blob }));
    await expect(downloadProject("h:0", "abc")).resolves.toBe(blob);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/banks\/h%3A0\/project$/);
    expect(init?.body).toBe('{"image_b64":"abc"}');
  });

  it("omits image_b64 for text specs and maps 404 through friendlyMessage", async () => {
    respond(404, { detail: "no bank" });
    await expect(downloadProject("h:0")).rejects.toThrow("Not found: no bank");
    expect(vi.mocked(fetch).mock.calls[0][1]?.body).toBe("{}");
  });
});

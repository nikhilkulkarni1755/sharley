import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createSpec, friendlyMessage } from "../lib/api";

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

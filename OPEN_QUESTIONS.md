# Open questions and assumptions (need your input or real keys)

Each item was coded around with a working fallback; none blocks the demo.

1. **Meta Model API**: model id, base URL and request format were not guessed. The adapter assumes an
   OpenAI-compatible `/chat/completions`; set `META_BASE_URL` / `META_MODEL` from dev.meta.ai/docs/models
   (`sharley/providers/openai_compat.py`). If the format differs, only that adapter changes.
2. **Gemini Interactions API**: request/response shape in `sharley/providers/gemini.py` is an assumption
   (`POST /interactions`, `generation_config.thinking_level`, `outputs[].text`). Verify against google-genai >= 2.3.0
   once `GEMINI_API_KEY` exists. `thinking_budget`, temperature, top_p/top_k and cached_content are never sent.
3. **Antigravity sandbox** is not implemented. Local Docker is the sandbox and is verified (no network, read-only
   root, app runs as `nobody`, unforgeable results). Needs the Antigravity API shape and a key.
4. **SubQ Snap 1.1** is wired as an OpenAI-compatible adapter (`SUBQ_BASE_URL`, `SUBQ_MODEL`); endpoint format unconfirmed.
5. **ASI:One Interactive Cards and Payment Protocol**: the ACP chat agents are built to the documented API
   (`agents/runtime.py`). The card wire format is unconfirmed, so cards go out as markdown text plus a structured dict
   isolated in `agents/cards.py`. Payment/Stripe is not built. Registering on Agentverse needs your account
   (mailbox connect in the Inspector) and the AIE Summit Submission Agent step is manual.
6. **The demo fixture uses a stand-in for the LLM test writer.** `evals/fixtures/demo.json` is real Docker output
   (sealed verdict, mutation scores, adopt/rollback decisions) but the test writer is a deterministic stand-in that
   unlocks subsets of the hand-written oracle suite, and the final 0.93 is partly by construction (mutants the oracle
   cannot kill are dropped as equivalent). It is labelled `source: oracle-stand-in`. Rebuild with real keys for an
   honest LLM number. The 0.90 target is therefore unverified for real model-written tests.
7. **Sandbox dependencies**: containers have no network, so implementer apps may only use what is baked into
   `sharley/runner/images/python.Dockerfile` (fastapi, uvicorn, httpx, pydantic, sqlalchemy, pyjwt, passlib). The node
   (nextjs) image and vitest parsing exist but are untested end to end.
8. **Web CSP** allows any `https:` `connect-src` and inline scripts (static export). Tighten to your API origin; the
   `_headers` check only runs on a real Cloudflare Pages deploy (`npx serve` ignores `_headers`).
9. **Cloudflare / Mac mini hosting**: Pages deploy and the tunnel to the API container were not run (no credentials).
   The API image is tested (`tests/deploy`). Note the Docker sandbox needs the host Docker socket, so run the API on the
   host (`sharley serve`) rather than in the container if you want live judging.
10. **Mongo**: tested against a fake collection only, not a live Atlas cluster.
11. **Second stack profile / second reference app**: nextjs profile exists, not exercised against a reference app.

# End-to-end analysis of the four example repos

Three measurements per repo, all stored here:
- `*.txt` (repo root of `test-runs/`): v0 deterministic stages, no model (before any fix, no keys).
- `live/*.txt`: v1, live model run (spec + bank) *before* the fixes. The bank was built without `--repo`.
- `live-v2/*.txt`: v2, same commands *after* the fixes, with `--repo`. Verifier chain: Meta `muse-spark-1.3` first, Claude fallback.

## How each example behaved and what went wrong

| Repo | v0 (static parse) | v1 (live, before fixes) | v2 (live, after fixes) |
|---|---|---|---|
| VAmPI | stack ok; **0 routes** (OpenAPI/connexion unseen) | 29 req, 99 tests; **7% of test paths were real routes** | 14 routes; 29 req, 78 tests; **86%** (examples 83%) |
| flask tutorial | stack unknown (no Docker); 8 routes ok | 22 req, 85 tests; tests assume a JSON API for an HTML app | 20 req; **bank refused (exit 3)**: R9 is an internal function, untestable over HTTP |
| full-stack-fastapi-template | **stack unknown (monorepo)**; 21 routes unprefixed; 4 env vars all noise; 1 schema | 31 req, 113 tests; **50%** real paths | stack ok; 23 prefixed routes; 20 real env vars; 16 schemas; 33 req, 122 tests; **86%** (examples 92%) |
| fastapi-realworld-example-app | 12 routes without `/articles`, `/users`, `/profiles`; 0 env vars | 32 req, 99 tests; **12%** real paths | 19 prefixed routes; 17 env vars; 37 req, 108 tests; **75%** |

## Root causes and the fix for each

1. **Tests guessed endpoint paths** (`os.environ.get('LOGIN_PATH','/login')`). The test writer only saw requirements. Fix: the parsed route surface is passed to the writer with an explicit "use only these paths, never invent one" rule, and `bank` warns when no `--repo` is given. Effect: 7% -> 86%, 50% -> 86%, 12% -> 75%.
2. **VAmPI had no routes** (routes live in OpenAPI YAML). Fix: parse `openapi*/swagger*` YAML/JSON. 0 -> 14 routes.
3. **Prefixes dropped** (`APIRouter(prefix=...)`, nested `include_router(..., prefix=...)`, multi-line calls, empty paths). Fix: resolve prefix chains across modules (cycle-safe). realworld 12 -> 19 correct routes.
4. **Monorepo not detected.** Fix: look for markers in subfolders. full-stack: unknown -> docker-api.
5. **Env vars wrong.** Fix: read pydantic `*Settings` fields and starlette `config("X")`, ignore test and frontend files. full-stack 4 noise -> 20 real; realworld 0 -> 17.
6. **Schemas missed** (SQLModel `table=True`). 1 -> 16.
7. **Noise in function lists** (React components, test functions). Excluded.
8. **Budget runaway risk.** Every paid call is metered into a persistent ledger with a hard cap (`SHARLEY_BUDGET_USD`); `sharley spend` shows it. A reasoning model returning `content: null` is now an error instead of a crash.

## Round 2: the planted-flaw backends (`sample-backends/`, results in `test-runs/samples/`)
Two homemade backends with known bugs, each with a fixed twin: a payments API for users and AI agents (double refund = logic flaw; `alg: none` token
accepted = CVE class) and electricity billing (3 of 12 houses silently billed 0). Tests are written from the plain-English spec plus the app's surface,
then run in the Docker sandbox against BOTH the flawed app and the fixed twin. A test that fails on the fixed twin is a false failure; a flaw is detected
when tests that pass on the twin fail on the flawed app.

| Run | What changed before it | Payments: failing on the CORRECT app | Payments: flaws caught | Electricity: failing on the correct app | Electricity: flaw caught |
|---|---|---|---|---|---|
| 1 | routes only | 63 of 81 (78%) | 1 of 2 (token) | 46 of 57 | no |
| 2 | + request bodies, response keys | 20 of 82 (24%) | 1 of 2 (refund) | 50 of 68 | no |
| 3 | + error messages, original spec text to writers | 4 of 90 (4%) | **2 of 2** | 15 of 70 (21%) | **yes** (2 tests) |

Playground banks are then calibrated (tests failing on the fixed twin are dropped: payments 90 to 85, electricity 70 to 55) and the tests that catch the flaw are
sealed on purpose (curated, not a claim about random splits). Verified through the real server: flawed code gives `Wrong Answer on sealed test N of M` in about 2 s,
fixed code gives `Accepted`. Against real GitHub clones of the published example repos the same verdicts come back in about 3 s.

## Round 2: image (camera) mode
- Synthetic whiteboard sketch: 10 requirements (7 drawn, 3 assumed).
- Your handwritten loan-flow notebook photo (iPhone JPEG, 4032x3024):
  | Provider | Result |
  |---|---|
  | First attempt | failed: `no content could be read` (Meta returned an empty description after 53 s) and Claude returned HTTP 400 |
  | After the fix, Claude only | 21 requirements (13 drawn, 8 assumed), 17 s; misread "ssn vault" as "SSN validity" and "unified identity" as "verified identity" |
  | After the fix, Meta first | 31 requirements (24 drawn, 7 assumed), 73 s; read both labels correctly; missed some arrow directions Claude caught |
  Outputs: `image-mode-loan-photo-claude-only.json`, `image-mode-loan-photo-meta.json`. Evidence text for images is the model's description of the region, not literal page text.

## Root causes found in round 2 and the fix for each
8. **Tests guessed request bodies and response keys** (63/81 false failures). The surface now includes request-body fields (required vs optional), response keys and documented error responses.
9. **Credentials and seeded ids never reached the writer** (electricity: 46/57 and 50/68 failing on both apps). Requirements are atomic, so setup facts in the spec were lost. Each writer now also receives the original spec text (capped at 6000 chars).
10. **Detecting tests landed in the visible examples**, so the flawed code was "Accepted". Playground banks seal the detecting tests (curation, labelled).
11. **Images were labelled `image/png` even when JPEG.** The media type is now read from the file's bytes on every provider.
12. **An empty image description counted as success**, so the chain never fell back. It now fails the step, retries, then escalates.
13. **Verdict hints were cut mid-word at 200 chars.** They now keep up to 320 chars and cut on a word boundary.
14. **A spend-cap error looked like an incomplete bank (422).** It is now a clear 503 with no retry; partial banks are an explicit choice (`allow_partial`).
15. **Latency:** chunked extraction runs in parallel; test writing uses 8 workers instead of 4; Meta (a slow reasoning model) is last for small steps. Reasoned from the code and measured timings, not re-benchmarked.
16. **Board honesty:** LIVE, RECORDED and PRE-BUILT chips; "Visible 25/25" and "Hidden 55/60" shown separately; end-of-run summary card; GitHub repo tab; project-zip download.

## Still wrong or not yet done (honest list)
- **No generated test has been run against a running copy of the four open-source repos.** False-failure rate on them is unmeasured (realworld and full-stack need Postgres; every repo needs its own dependencies in a runner image). Only the two sample backends have been executed against.
- **Detection is noisy run to run.** Payments caught a different flaw in runs 1 and 2. Three runs is not a rate; measure over more seeds.
- **Calibration and sealing use ground truth** (the fixed twin and the known flaw). That is a demo curation, not something Sharley can do for an unknown app.
- **The skill-loop timeline in the demo fixture uses a scripted stand-in writer.** `sharley improve` has not been run with a real model.
- **Global `/api` prefix** set at runtime is invisible to static analysis.
- **Requirements about internal functions** (flask R9, R10, R13, R14) are untestable over HTTP; a "not testable, with reason" waiver is still needed.
- `sharley.yaml` for existing repos still states the profile boot command, not the repo's own.
- Sponsor adapters never exercised: Gemini, SubQ, Atlas, Cloudflare Pages. Fetch agents start locally but are not registered.

## Spend
`sharley spend` ledger: see below. Claude is priced at published rates; Meta is priced with a deliberately high placeholder ($10/$50 per million tokens) because its
pricing page could not be fetched, so real Meta cost is lower. The cap was raised to $200 on request; it no longer protects the budget.

```
spent $23.4606 of $200.00 cap over 159 calls
  meta: $18.2366 (71505 in / 350431 out tokens)
  anthropic: $5.2240 (147557 in / 492889 out tokens)
```

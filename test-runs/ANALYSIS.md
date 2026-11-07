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

## Still wrong or not yet done (honest list)
- **No generated test has been executed against a running copy of these repos yet.** So false-failure rate on the unmodified repos is unmeasured. realworld and full-stack need Postgres; all need their dependencies in a per-repo runner image. This is the next engineering step.
- **Global `/api` prefix** set at runtime (realworld, full-stack) is invisible to static analysis.
- **Requirements about internal functions** (flask R9/R10/R13/R14) make the bank fail. Needs a "not testable: reason" waiver.
- The flask tutorial is HTML/session based; a JSON-API test style is a poor fit.
- `sharley.yaml` for existing repos still states the profile boot command, not the repo's own.

## Spend
`sharley spend` ledger after the v2 run: $7.70 of the $15 cap over 48 calls: Claude $1.82 (priced at published rates) and Meta $5.88 (priced with a deliberately high placeholder of $10/$50 per million tokens, so real Meta cost is lower). The earlier v1 run predates the meter (Anthropic, small); check the Anthropic console for the exact figure.

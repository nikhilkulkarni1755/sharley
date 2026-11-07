# Sharley

Independent verifier for AI-written code. Sharley turns any spec (text, one-line idea, codebase or a sketch)
into a requirement-tagged test bank, shows the implementing agent only the **example** tests, and judges its work
against **sealed hidden tests**, LeetCode style, on a different model family than the implementer. It proves its
tests have teeth with a mutation score and improves its own test-writing skills only when held-out evaluation confirms it.

```
spec ──▶ requirements R1..Rn (observed | inferred, coverage %) ──▶ planner/queue/workers ──▶ test bank
   example tests (~30%) ──▶ implementer          sealed tests (~70%) stay server-side
   submission ──▶ tamper check ──▶ clean Docker sandbox ──▶ Accepted | Wrong Answer on sealed test 37 of 58 (R7) | ...
```

## Quick start

```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # add ".[agents]" for the Fetch.ai uAgents
cp .env.example .env               # keys are optional; SHARLEY_OFFLINE=1 forces local fallbacks
sharley images                     # build the sandbox runner images (needs Docker)
pytest                             # unit + real-Docker tests (docker-marked tests skip without a daemon)
```

## Use it

```
sharley spec  --text idea.txt --out spec.json        # or --image sketch.png / --repo ./project
sharley bank  --spec spec.json --workspace ./impl --stack docker-api --bank-out sealed.json
# implementer works in ./impl against the example tests only
sharley check --bank-file sealed.json --workspace ./impl --implementer-model gemini-4-argon --implementer-family google
sharley watch --bank-file sealed.json --implementer-model ... --implementer-family ...   # auto revert PR on failure
sharley serve                                       # HTTP/SSE API for the board (web/)
```

`.github/workflows/sharley.yml` is the merge gate: add `SHARLEY_BANK_JSON` as a secret (it is inert without it).
Keep the sealed bank file out of the repo and out of the implementer's workspace.

## Modules

| Path | Job |
|---|---|
| `sharley/schemas` | Pydantic: Spec, Requirement, TestBank, Verdict, Mutant, SkillVersion |
| `sharley/harness`, `providers` | `ModelProvider`, typed validate/retry/escalate `Step`, fallback chains, health checks |
| `sharley/intake`, `profiles` | any input to hashed `spec.json`; nextjs and docker-api profiles |
| `sharley/planner`, `generator` | tasks, MongoDB/JSON queue, parallel workers, traceability, functional/security/env tests |
| `sharley/judge`, `runner` | sealed split, leak scan, tamper check, verdicts; isolated Docker sandbox |
| `sharley/mutation`, `evals` | operators, train/heldout split, graders, reference notes app, oracle suite, fixtures |
| `sharley/skills` | versioned skills, reflection on train survivors, adopt/rollback on held-out score |
| `sharley/gate`, `api`, `implementer` | CLI, watch, merge gate, HTTP API, the agent being judged |
| `agents` | Fetch.ai Intake / Test Author / Judge agents (ACP) + `/api/chat` fallback |
| `web` | Next.js board (static export): intake, judge, eval |

## Testing and deployment checks

- `pytest` covers each module for intended use and for misuse (hostile model output, path traversal, prompt injection,
  forged results, secret leakage). A hostile app inside the sandbox cannot read or edit tests or forge its verdict.
- `pytest tests/deploy` builds the API image and probes it over real HTTP; `web/` has Vitest and Playwright
  (mocked project in CI, `deployed` project via `DEPLOY_URL`/`API_URL`, see `web/README.md`).
- Everything degrades to local fallbacks: see `OPEN_QUESTIONS.md` for what needs your keys or decisions.

Built during the AIE Code Summit 2026 Hackathon; see `BUILT_TODAY.md`.

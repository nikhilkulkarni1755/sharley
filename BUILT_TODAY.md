# Built today

Every component of Sharley was written during the AIE Code Summit 2026 Hackathon.
Each row links to the merged PR that introduced it (`git log --merges` has timestamps).

| Component | Path | PR |
|---|---|---|
| Typed schemas | `sharley/schemas/` | #1 |
| Model harness | `sharley/harness/` | #3 |
| Provider adapters + chains | `sharley/providers/` | #4 |
| Storage (Mongo + JSON fallback) | `sharley/storage/` | #5 |
| Stack profiles | `sharley/profiles/` | #6 |
| Intake (spec extraction) | `sharley/intake/` | #7 |
| Test generator | `sharley/generator/` | #8 |
| Planner + queue + workers | `sharley/planner/` | #9 |
| Sandbox runner (local Docker) | `sharley/runner/` | #10 |
| Judge (sealed tests + verdicts) | `sharley/judge/` | #12 |
| Reference notes app + oracle | `evals/` | #13 |
| Mutation engine + graders | `sharley/mutation/, evals/graders/` | #14 |
| Versioned skills + rollback | `sharley/skills/` | #15 |
| Merge-gate CLI (spec/bank/check) | `sharley/gate/` | #16 |
| Merge gate watch + GitHub Action | `sharley/gate/watch.py, .github/workflows/sharley.yml` | #17 |
| Implementer agent | `sharley/implementer/` | #18 |
| HTTP API + SSE | `sharley/api/` | #19 |
| Demo fixtures (real Docker runs) | `evals/fixtures/` | #23 |
| Fetch.ai uAgents + chat fallback | `agents/` | #24 |
| API deployment image | `deploy/` | #25 |
| Next.js board + Playwright/Vitest | `web/` | #21 |
| Sandbox isolation hardening | `sharley/runner/docker.py` | #11 |
| Pytest summary classification fix | `sharley/runner/parse.py` | #22 |

Every row is a merged PR; `git log --merges --format='%h %ad %s' --date=iso` gives timestamps. Nothing here was
copied from other projects.

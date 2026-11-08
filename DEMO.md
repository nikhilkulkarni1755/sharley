# Demo: 60 seconds

Track: **Trust but Verify** (primary), with **The System That Gets Better** as the second story. Meta Muse Spark is the verifier.

## Run this before recording
```
# terminal 1 (Docker running)
SHARLEY_CORS_ORIGINS=http://localhost:3005 .venv/bin/python -m sharley serve --port 8000
# terminal 2
cd web && NEXT_PUBLIC_API_URL=http://localhost:8000 npx next dev -p 3005      # http://localhost:3005
```
Pre-run the photo through Intake once, off camera (about 75 s with Meta), so the finished result is on screen.
Check: Playground shows both backends; Eval tab loads.

## The 60 seconds (say the quoted lines; minimal fluff)
| Time | On screen | Say |
|---|---|---|
| 0-8 | Header: "Independent Security and QA verifier for AI Code!" | "AI writes code faster than anyone can check it. Sharley is an independent verifier: different model family than the coder, and hidden tests the coder never sees." |
| 8-20 | Intake: photo of the hand-drawn loan flow, finished result: 31 requirements, drawn vs assumed badges | "I photographed my notebook. Meta's Muse Spark read my handwriting into 31 requirements, each tagged: drawn by me, or assumed by the model, never silently invented." |
| 20-35 | Playground, Electricity: Run sealed tests; tiles flip; banner | "Here is a real billing backend. It passes every test you can see, 15 of 15. The hidden tests fail: three of twelve houses get free electricity because an unknown tariff silently bills zero. Nobody's own tests caught it." |
| 35-45 | Edit the tariff lookup line, Run again: Accepted | "One line fixed, hidden tests rerun in two seconds: accepted. The coding agent can't edit, read or skip those tests, so it has to actually implement the spec." |
| 45-55 | Slide or `test-runs/`: the three stats below | "And it gets better with evidence: false failures on a correct app went from 78 percent to 4, and a flaw it used to miss it now catches. A new rule is only kept if held-out mutants improve; otherwise it's rolled back." |
| 55-60 | Download project zip, or the repo | "Meta writes the tests, Claude Code builds against them. Everything here was built today." |

## Three recorded stats that show evolution (all in `test-runs/`)
1. **Tests got truer, and flaws got found** (same specs, three generations as we fixed the pipeline)
   | Run | Payments: tests failing on the CORRECT app | Payments: planted flaws caught | Electricity: failing on the correct app | Electricity: flaw caught |
   |---|---|---|---|---|
   | 1 | 63 of 81 (78%) | 1 of 2 | 46 of 57 | no |
   | 2 | 20 of 82 (24%) | 1 of 2 (the other one) | 50 of 68 | no |
   | 3 | 4 of 90 (4%) | **2 of 2** | 15 of 70 (then calibrated away) | **yes** |
   What changed: the writer now receives request bodies, response keys and error messages, and the original spec text (credentials, ids).
2. **Tests anchored to real code** (share of endpoint paths in the tests that really exist), before to after route/prefix/OpenAPI parsing:
   VAmPI 7% to 86%, full-stack-fastapi-template 50% to 86%, realworld app 12% to 75%.
3. **Skill loop: adopt only what held-out evaluation confirms** (real Docker runs; the test writer in this recording is a scripted stand-in, labelled RECORDED on the Eval tab):
   baseline 0.60, v1 adopted 0.73, v2 rolled back (no gain), v3 adopted 0.93, v4 rolled back (false failures rose 0 to 0.08).

## What we used (truthfully)
| Sponsor | Use | Status |
|---|---|---|
| **Meta Model API** | `muse-spark-1.3`: first verifier for reading the photo and writing tests; the board shows it as the bank author | real, live |
| Anthropic Claude | fallback verifier, fast small steps, second image reader; Claude Code built the board and plays the implementer | real, live |
| MongoDB | repository and task queue, tested against a real MongoDB container | local container; Atlas not connected |
| Fetch.ai | three agents on the chat protocol, start locally | built; register on Agentverse to count |
| Google, Subquadratic, Cloudflare | adapters / scripts written | not exercised: do not claim |

## If something breaks
Switch the Judge tab to Replay (recorded, no model, no sandbox), or run the Playground, which needs no model.

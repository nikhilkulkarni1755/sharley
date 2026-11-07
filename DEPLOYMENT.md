# Deployment: from local containers to production

Sharley runs untrusted code (the implementer's app) and holds a secret (the sealed tests). Deployment is mostly about
keeping those two apart and keeping paid model calls under control.

## What runs today (local)

```
browser ──> web (static)  ──> API (host process: `sharley serve`) ──> Docker daemon on the same host
                                   │                                      └─ one throw-away sandbox container per judging run
                                   └─ JSON store or Mongo, ledger.json (spend cap)
```

Each judging run: a tar of the app + the tests is piped on stdin into a container with no network, no bind mounts,
read-only root, dropped capabilities, memory/CPU/pids limits and a wall-clock timeout. The app runs as `nobody`; the
harness runs as root with only SETUID/SETGID/CHOWN, so the app cannot read, edit or forge the test results.

## What must change before a public deployment

| # | Gap in the code today | Why it matters | Change |
|---|---|---|---|
| 1 | **No auth or rate limit on the API.** `/api/specs`, `/api/banks`, `/api/chat` call paid models. | Anyone who finds the URL can burn the budget. | API key or Turnstile at the edge, per-key quotas, request-size caps (exist), and the spend cap stays as the last line. |
| 2 | Judging runs inside API threads; run events and chat sessions live in process memory. | Restart loses runs; two API instances cannot share them. | Put jobs on the existing Mongo `queue`; runner workers write events to Mongo; the SSE endpoint reads from Mongo. |
| 3 | The API needs the host Docker socket. | Mounting the socket into a public-facing container is root on the host. | Only **runner workers** touch Docker (or a microVM service). The public API never does. |
| 4 | Spend ledger is a local JSON file. | Several instances each think they have the full budget. | Keep the ledger in Mongo with an atomic `$inc`. |
| 5 | Sealed banks are stored in plain JSON/Mongo. | A DB leak exposes the hidden tests. | Encrypt the sealed code with a KMS/key held only by runner workers; the API only ever sees opaque tiles. |
| 6 | Runner images carry a fixed dependency list. | Real repos need their own deps (and Postgres, etc.). | Build per-repo images in a separate **build tier** (network on, no secrets), push to a registry by digest; the **run tier** stays network-off. |
| 7 | CORS defaults to localhost; CSP allows any https `connect-src`. | Wrong origin or too-open CSP. | Set `SHARLEY_CORS_ORIGINS` to the Pages URL; tighten CSP to the API origin. |

## Target topology

```
Cloudflare Pages (static web) ──> Cloudflare (WAF, rate limit, Turnstile)
                                       │ https
                                  API tier (stateless, N instances: Cloud Run / Fly / the Mac mini via tunnel)
                                       │ writes jobs, reads events
                                  MongoDB Atlas  (specs, banks[encrypted sealed], runs, events, queue, ledger)
                                       │ pulls jobs
                                  Runner tier (separate hosts or microVMs)
                                       └─ per-run sandbox: no network, read-only, capped, killed on timeout
                                  Build tier (network on, no secrets) ──> image registry (digest-pinned)
```

## Sandbox options, weakest to strongest isolation

1. **Docker on a dedicated host** (what we have). Fine for a demo and for trusted users; containers share the host kernel.
2. **Docker + gVisor (`runsc`)**: same flags, user-space kernel; a cheap hardening step on any Linux runner host.
3. **Firecracker-class microVMs** (Fly Machines, AWS Fargate/Lambda, E2B, Modal sandboxes): one VM per run, strongest
   isolation for untrusted internet code. Recommended for a public service.
4. **Google Antigravity sandbox** (the hackathon option): Google-hosted Linux sandbox, no host to manage. Not wired yet;
   `runner/base.py::Sandbox` is the interface, so it is an adapter, not a rewrite.

## Interim plan (hackathon, "local containers, then deploy")

- Frontend: `npm run build` -> `wrangler pages deploy out` (Cloudflare Pages), `NEXT_PUBLIC_API_URL` = API URL.
- Backend: `sharley serve` on the Mac mini with Docker, exposed through the existing Cloudflare tunnel; set
  `SHARLEY_CORS_ORIGINS`, add the API key check (#1) first, keep `SHARLEY_BUDGET_USD` low, and cap concurrent sandboxes
  (2-3) so a burst cannot starve the host.
- Replay mode (`/api/demo`) needs no backend or keys, so the stage demo survives any outage.

## Capacity and failure behaviour to decide

- Concurrency per runner host = CPUs / 1 (each sandbox is capped at 1 CPU, 512 MB). Queue the rest; show queue position.
- A sandbox that exceeds its timeout is killed and reported `Time Limit Exceeded`; the container is always removed.
- If every model provider is down the API returns a clear retryable 503 and the board falls back to replay mode.
- Per-run cost is already recorded; surface it in the UI and refuse new runs once the cap is reached.

# Sharley board

Static Next.js board (Playground, Intake, Judge, Eval) over the Sharley API. It is a window into the verifier: sealed tests never reach the browser.

- **Playground** (default tab): pick a sample backend from `GET /api/samples`, edit its code (kept per backend in `sessionStorage`) and run the sealed tests against your edits.
- **Intake** also accepts a camera photo (`Take a photo`), a live webcam capture (`Use webcam`, needs `camera=(self)` in `Permissions-Policy`) and `Try the sample sketch` (`public/sample-sketch.png`).

## Develop

```sh
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # API base, default http://localhost:8000
```

The API must allow the page origin via CORS (`create_app(..., cors_origins=[...])`; default `http://localhost:3000`).

## Test

```sh
npm run lint
npm test                                  # vitest: verdict, event reducer, curve, files, API client, components
npx playwright install chromium
npm run e2e                               # mocked project: builds the export, serves it on :3100, mocks the API
DEPLOY_URL=https://sharley.pages.dev API_URL=https://api.example.com npm run e2e:deployed
```

The `deployed` project skips when `DEPLOY_URL` is unset. It checks the 200 response, console errors, security headers, the Eval tab from the replay fixture, and `GET $API_URL/api/health`.

## Deploy to Cloudflare Pages

```sh
NEXT_PUBLIC_API_URL=https://api.example.com npm run build   # static export to out/
npx wrangler pages deploy out --project-name sharley-board
```

`public/_headers` ships the CSP and other security headers. Its `connect-src` allows any `https:` origin plus `http://localhost:8000`; tighten it to your API origin. Add the Pages origin to the API's CORS list.

To check the deploy without publishing, run `npx wrangler pages deploy out --project-name sharley-board --dry-run` if your wrangler version supports it, otherwise serve `out/` locally with `npx serve out` and run the deployed project against it.

#!/bin/zsh
# One-command public demo: API (public mode, rate-limited) + static board, each behind a free Cloudflare quick tunnel.
# Needs: docker running, cloudflared, node, the sealed banks already built (.sharley/). Stop with Ctrl-C.
set -e
cd "$(dirname "$0")/.."
export SHARLEY_PUBLIC_MODE=1 SHARLEY_ADMIN_KEY="${SHARLEY_ADMIN_KEY:-$(openssl rand -hex 16)}"
export SHARLEY_CORS_ORIGIN_REGEX='https://[a-z0-9-]+\.trycloudflare\.com' SHARLEY_RUNS_PER_MINUTE=20 SHARLEY_MAX_CONCURRENT_RUNS=3
trap 'kill $(jobs -p) 2>/dev/null' EXIT
python -m sharley serve --port 8000 & 
cloudflared tunnel --no-autoupdate --url http://localhost:8000 > /tmp/sharley-api-tunnel.log 2>&1 &
API=""; until [ -n "$API" ]; do API=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/sharley-api-tunnel.log | head -1); sleep 1; done
echo "API:  $API"
NEXT_PUBLIC_API_URL="$API" npm --prefix web run build
npx --yes serve web/out -l 3100 > /dev/null 2>&1 &
cloudflared tunnel --no-autoupdate --url http://localhost:3100 > /tmp/sharley-web-tunnel.log 2>&1 &
WEB=""; until [ -n "$WEB" ]; do WEB=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/sharley-web-tunnel.log | head -1); sleep 1; done
echo "JUDGES LINK:  $WEB"
echo "Paid endpoints (spec/bank/chat) need header X-Sharley-Key: $SHARLEY_ADMIN_KEY (kept off the public UI)."
wait

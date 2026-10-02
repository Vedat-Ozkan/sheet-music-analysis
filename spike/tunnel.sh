#!/usr/bin/env bash
# Start or stop the spike server behind a temporary Cloudflare tunnel.
# The public address changes on every start and is printed and saved to out/tunnel.url.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out

stop() {
  for name in spike-server tunnel; do
    if [ -f "out/$name.pid" ]; then
      kill "$(cat "out/$name.pid")" 2>/dev/null || true
      rm -f "out/$name.pid"
    fi
  done
  rm -f out/tunnel.url
}

case "${1:-}" in
  start)
    stop
    nohup out/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8765 > out/tunnel.log 2>&1 &
    echo $! > out/tunnel.pid
    url=""
    for _ in $(seq 1 30); do
      url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' out/tunnel.log | head -1 || true)
      [ -n "$url" ] && break
      sleep 1
    done
    [ -n "$url" ] || { echo "The tunnel did not report an address; see out/tunnel.log" >&2; stop; exit 1; }
    echo "$url" > out/tunnel.url
    PUBLIC_BASE_URL="$url" nohup .venv/bin/python -m spike.server > out/spike-server.log 2>&1 &
    echo $! > out/spike-server.pid
    echo "Connector URL: $url/mcp"
    ;;
  stop)
    stop
    echo "Stopped."
    ;;
  *)
    echo "usage: spike/tunnel.sh start|stop" >&2
    exit 2
    ;;
esac

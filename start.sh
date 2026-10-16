#!/bin/sh
set -eu
APP="/opt/geoser/tecnologia-geoser"
PORT="3014"
LOG="$APP/data/server.log"
PIDFILE="$APP/data/server.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    exit 0
  fi
fi

if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  exit 0
fi

cd "$APP"
nohup env HOST=0.0.0.0 PORT="$PORT" PYTHONUNBUFFERED=1 /usr/bin/python3 "$APP/server.py" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
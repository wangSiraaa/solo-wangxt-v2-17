#!/usr/bin/env bash
# 停止演示环境（不影响 .localpg 中手动管理的 PostgreSQL，除非传入 --with-db）
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/.run"

for name in api worker web; do
  if [ -f "$RUN_DIR/$name.pid" ]; then
    PID=$(cat "$RUN_DIR/$name.pid")
    kill "$PID" 2>/dev/null || true
    rm -f "$RUN_DIR/$name.pid"
  fi
done
# 兜底：按命令行匹配清理（用括号模式避免匹配到自身）
for p in $(ps -eo pid,args | grep -E "[u]vicorn app.main:app|[r]un_worker.py|[n]ext start" | awk '{print $1}'); do
  kill "$p" 2>/dev/null || true
done

if [ "${1:-}" = "--with-db" ] && [ -x "$ROOT/.localpg/usr/lib/postgresql/15/bin/pg_ctl" ]; then
  "$ROOT/.localpg/usr/lib/postgresql/15/bin/pg_ctl" -D "$ROOT/.localpg/data" stop || true
fi
echo "已停止演示服务。"

#!/usr/bin/env bash
# 一键启动本地演示：PostgreSQL + 初始化数据 + FastAPI + worker + Next.js
# 用法：scripts/start_demo.sh [--reset]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PG_HOME="$ROOT/.localpg"
PG_BIN="$PG_HOME/usr/lib/postgresql/15/bin"
PGRUN="$PG_HOME/run"
export LD_LIBRARY_PATH="$PG_HOME/usr/lib/aarch64-linux-gnu:$PG_HOME/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PATH="$PG_BIN:$PATH"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

# 1. Python 虚拟环境
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "创建 Python venv ..."
  python3 -m venv --without-pip "$ROOT/.venv"
  if [ ! -f /tmp/get-pip.py ]; then
    curl -sS -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
  fi
  "$ROOT/.venv/bin/python" /tmp/get-pip.py -q
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
fi

# 2. PostgreSQL（若系统已有 5433 上的实例可复用，否则本地免 root 安装）
if [ -x "$PG_BIN/postgres" ]; then
  "$ROOT/scripts/setup_postgres_local.sh"
else
  if ! pg_isready -h 127.0.0.1 -p 5433 >/dev/null 2>&1; then
    echo "未找到本地 PostgreSQL，且系统未安装；运行 scripts/setup_postgres_local.sh 或自行准备。"
    exit 1
  fi
fi

# 3. 初始化 / 重置数据库
if [ "${1:-}" = "--reset" ] || ! "$PG_BIN/psql" -h "$PGRUN" -p 5433 -U postgres -lqt 2>/dev/null | grep -q consent_demo; then
  (cd "$ROOT/backend" && "$ROOT/.venv/bin/python" init_db.py)
fi

# 4. 停止旧进程
"$ROOT/scripts/stop_demo.sh" || true

# 5. FastAPI
(cd "$ROOT/backend" && nohup "$ROOT/.venv/bin/uvicorn" app.main:app \
   --host 127.0.0.1 --port 8000 > "$RUN_DIR/api.log" 2>&1 & echo $! > "$RUN_DIR/api.pid")
# 6. worker
(cd "$ROOT/backend" && CONSENT_EXPORT_PROCESSING_SECONDS="${CONSENT_EXPORT_PROCESSING_SECONDS:-8}" \
   nohup "$ROOT/.venv/bin/python" run_worker.py > "$RUN_DIR/worker.log" 2>&1 & echo $! > "$RUN_DIR/worker.pid")
# 7. Next.js（未构建则构建）
if [ ! -d "$ROOT/frontend/.next" ]; then
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build)
fi
(cd "$ROOT/frontend" && nohup npm run start > "$RUN_DIR/web.log" 2>&1 & echo $! > "$RUN_DIR/web.pid")

echo "启动中..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null && curl -sf -o /dev/null http://127.0.0.1:3000/; then
    cat <<EOF

✅ 演示环境已启动：
   前端（Next.js）  : http://127.0.0.1:3000
   后端 API（FastAPI）: http://127.0.0.1:8000/docs
   日志目录         : $RUN_DIR/{api,worker,web}.log
   停止             : scripts/stop_demo.sh
   重置演示数据     : curl -X POST http://127.0.0.1:8000/api/dev/reset
EOF
    exit 0
  fi
  sleep 1
done
echo "启动超时，请检查 $RUN_DIR 下日志"
exit 1

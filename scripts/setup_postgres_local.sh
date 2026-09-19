#!/usr/bin/env bash
# 免 root 在用户目录准备 PostgreSQL 15（Debian/Ubuntu 系）。
# 已存在则直接复用。数据目录：项目根 .localpg/data，监听 127.0.0.1:5433。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PG_HOME="$ROOT/.localpg"
PG_BIN="$PG_HOME/usr/lib/postgresql/15/bin"
PGDATA="$PG_HOME/data"
PGRUN="$PG_HOME/run"
PORT=5433

if [ -x "$PG_BIN/postgres" ] && [ -f "$PGDATA/PG_VERSION" ]; then
  echo "PostgreSQL 已就绪：$PG_BIN"
else
  mkdir -p "$PG_HOME/debs"
  TMPLISTS="$(mktemp -d)"
  echo "下载 postgresql-15 deb 包到 $PG_HOME/debs ..."
  apt-get -o Dir::State::Lists="$TMPLISTS/lists" -o Dir::Cache="$TMPLISTS" \
          -o Dir::Cache::Archives="$TMPLISTS/archives" update >/dev/null
  (cd "$PG_HOME/debs" && apt-get -o Dir::State::Lists="$TMPLISTS/lists" \
        download postgresql-15 postgresql-client-15 libpq5)
  for d in "$PG_HOME"/debs/*.deb; do dpkg-deb -x "$d" "$PG_HOME"; done
  mkdir -p "$PGRUN"
  "$PG_BIN/initdb" -D "$PGDATA" -U postgres --auth=trust -E UTF8 --locale=C
  cat >> "$PGDATA/postgresql.conf" <<EOF
listen_addresses = '127.0.0.1'
port = $PORT
unix_socket_directories = '$PGRUN'
fsync = off
synchronous_commit = off
full_page_writes = off
EOF
fi

export LD_LIBRARY_PATH="$PG_HOME/usr/lib/aarch64-linux-gnu:$PG_HOME/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"

if ! "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$PG_HOME/postgres.log" -w start
  sleep 1
fi
"$PG_BIN/psql" -h "$PGRUN" -p "$PORT" -U postgres -tc "SELECT 1" >/dev/null
echo "PostgreSQL 运行中：127.0.0.1:$PORT（socket $PGRUN）"

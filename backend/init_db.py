#!/usr/bin/env python3
"""初始化数据库：执行 schema.sql + seed.sql（幂等：先 DROP DATABASE）。"""
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    here = Path(__file__).resolve().parent
    schema_sql = (here / "schema.sql").read_text(encoding="utf-8")
    seed_sql = (here / "seed.sql").read_text(encoding="utf-8")
    base_url, _ = settings.database_url.rsplit("/", 1)

    print(f"重建数据库 consent_demo：{settings.database_url}")
    with psycopg.connect(base_url + "/postgres", autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS consent_demo")
        conn.execute("CREATE DATABASE consent_demo")
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(schema_sql)
        conn.execute(seed_sql)
        conn.commit()
    Path(settings.export_dir).mkdir(parents=True, exist_ok=True)
    print("完成：schema + 演示种子数据已加载。")


if __name__ == "__main__":
    main()

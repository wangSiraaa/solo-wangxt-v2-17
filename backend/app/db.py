from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """同步数据库连接（短事务）。psycopg3 默认即事务模式：with get_conn() as conn 提交。"""
    conn = psycopg.connect(get_settings().database_url, row_factory=dict_row, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def tx(conn: psycopg.Connection):
    """显式保存点，便于在一个连接内分段提交。"""
    with conn.transaction():
        yield

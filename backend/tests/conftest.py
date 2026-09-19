"""端到端测试前置：重置数据库并提供 TestClient。

依赖本地 PostgreSQL（见 README“免 root 启动 PostgreSQL”）。
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("CONSENT_DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/consent_demo")
os.environ.setdefault("CONSENT_EXPORT_DIR", str(BACKEND / "data" / "exports_test"))
os.environ.setdefault("CONSENT_EXPORT_PROCESSING_SECONDS", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def _app_client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(_app_client):
    # 每个测试前重置到 seed 初始状态，保证用例彼此独立
    r = _app_client.post("/api/dev/reset")
    assert r.status_code == 200, r.text
    yield _app_client


H = {
    "P1001": {"X-Test-Identity": "participant-1001"},
    "P1002": {"X-Test-Identity": "participant-1002"},
    "R2001": {"X-Test-Identity": "researcher-2001"},
    "R2002": {"X-Test-Identity": "researcher-2002"},
    "ADMIN": {"X-Test-Identity": "admin-3001"},
}

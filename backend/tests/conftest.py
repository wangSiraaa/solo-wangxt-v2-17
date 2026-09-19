import os
import tempfile

# 必须在导入 app 之前设置：测试不启动后台 Worker，数据库指向临时目录
_TMP = tempfile.mkdtemp(prefix="rdp-test-")
os.environ["RUN_WORKER"] = "0"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/api-test.db"
os.environ["EXPORT_DIR"] = os.path.join(_TMP, "exports")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config, models
from app.db import Base
from app.seed import seed
from app.utils import utcnow


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    """每个测试一个独立的 SQLite 文件库 + 独立导出目录。"""
    monkeypatch.setattr(config, "EXPORT_DIR", str(tmp_path / "exports"))
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        seed(session)
        session.commit()
    return factory


@pytest.fixture()
def session(session_factory):
    with session_factory() as s:
        yield s


def make_grant(
    session,
    *,
    researcher_id="R-101",
    dataset_id="DS-CARDIO-2024",
    purpose_code="cardio",
    days_valid=7,
):
    from datetime import timedelta

    req = models.AccessRequest(
        researcher_id=researcher_id,
        project_title="测试项目",
        dataset_id=dataset_id,
        purpose_code=purpose_code,
        status="approved",
    )
    session.add(req)
    session.flush()
    grant = models.Grant(
        request_id=req.id,
        researcher_id=researcher_id,
        dataset_id=dataset_id,
        purpose_code=purpose_code,
        granted_by="A-001",
        expires_at=utcnow() + timedelta(days=days_valid),
    )
    session.add(grant)
    session.flush()
    return grant

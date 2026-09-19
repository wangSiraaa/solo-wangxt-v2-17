"""导出队列的权限检查点：排队时、执行前、提交前。"""

import os
import threading
import time

import pytest

from app import models
from app.services.consent import set_consent
from app.services.exports import process_one, queue_export, run_pending_exports
from app.services.permissions import PermissionDenied, evaluate_grant
from tests.conftest import make_grant


def test_queue_denied_when_consent_already_withdrawn(session):
    set_consent(session, participant_id="P-001", purpose_code="cardio",
                status="withdrawn", actor_id="P-001")
    grant = make_grant(session)
    with pytest.raises(PermissionDenied) as exc_info:
        queue_export(session, grant=grant, actor_id="R-101")
    assert "consent_withdrawn" in exc_info.value.decision.reasons
    assert exc_info.value.decision.withdrawn_participants == ["P-001"]


def test_expired_grant_denied(session):
    grant = make_grant(session, days_valid=-1)  # 已过期
    decision = evaluate_grant(session, grant)
    assert not decision.allowed
    assert "grant_expired" in decision.reasons
    with pytest.raises(PermissionDenied):
        queue_export(session, grant=grant, actor_id="R-101")


def test_export_completes_and_csv_contains_only_consented_rows(session_factory):
    with session_factory() as session:
        grant = make_grant(session)
        job = queue_export(session, grant=grant, actor_id="R-101")
        job_id = job.id
        session.commit()

    results = run_pending_exports(session_factory, delay=0)
    assert results == [(job_id, "completed")]

    with session_factory() as session:
        job = session.get(models.ExportJob, job_id)
        assert job.status == "completed"
        assert job.row_count == 6  # DS-CARDIO-2024 的 6 位参与者
        link = session.query(models.DownloadLink).filter_by(export_job_id=job_id).one()
        assert link.token
        with open(job.file_path, encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        assert len(lines) == 1 + 6  # 表头 + 6 行


def test_withdrawal_during_execution_caught_by_checkpoint(session_factory):
    """撤回与导出并发：导出执行窗口内撤回，提交前检查点必须拦截。"""
    with session_factory() as session:
        grant = make_grant(session)
        job = queue_export(session, grant=grant, actor_id="R-101")
        job_id = job.id
        session.commit()

    result_holder = {}

    def run():
        result_holder["status"] = process_one(session_factory, job_id, delay=1.0)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.3)  # 导出已进入执行窗口（检查点 A 已通过）

    with session_factory() as session:
        set_consent(session, participant_id="P-003", purpose_code="cardio",
                    status="withdrawn", actor_id="P-003")
        session.commit()

    thread.join(timeout=10)
    assert result_holder["status"] == "cancelled"

    with session_factory() as session:
        job = session.get(models.ExportJob, job_id)
        assert job.status == "cancelled"
        assert "consent_withdrawn" in job.cancel_reason
        # 半成品文件已删除，未签发下载链接
        from app import config

        partial = os.path.join(config.EXPORT_DIR, f"export-{job_id}.csv")
        assert not os.path.exists(partial)
        assert session.query(models.DownloadLink).filter_by(export_job_id=job_id).count() == 0
        cancel_events = session.query(models.AccessEvent).filter_by(
            event_type="export_cancelled", export_job_id=job_id
        ).all()
        assert cancel_events and cancel_events[0].detail["withdrawn_participants"] == ["P-003"]

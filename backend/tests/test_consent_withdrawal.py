"""授权版本链与撤回语义。"""

from app import models
from app.services.consent import set_consent
from app.services.exports import queue_export
from app.services.permissions import current_consent_status
from tests.conftest import make_grant


def test_consent_versioning(session):
    assert current_consent_status(session, "P-001", "cardio") == "granted"

    v2, _ = set_consent(
        session, participant_id="P-001", purpose_code="cardio",
        status="withdrawn", actor_id="P-001",
    )
    assert v2.version == 2
    assert current_consent_status(session, "P-001", "cardio") == "withdrawn"

    v3, _ = set_consent(
        session, participant_id="P-001", purpose_code="cardio",
        status="granted", actor_id="P-001",
    )
    assert v3.version == 3
    assert current_consent_status(session, "P-001", "cardio") == "granted"

    # 幂等：重复撤回不产生新版本
    set_consent(session, participant_id="P-001", purpose_code="cardio",
                status="withdrawn", actor_id="P-001")
    v, _ = set_consent(session, participant_id="P-001", purpose_code="cardio",
                       status="withdrawn", actor_id="P-001")
    assert v.version == 4
    count = session.query(models.ConsentVersion).filter_by(
        participant_id="P-001", purpose_code="cardio"
    ).count()
    assert count == 4


def test_withdraw_cancels_queued_exports(session):
    grant = make_grant(session)
    job1 = queue_export(session, grant=grant, actor_id="R-101")
    job2 = queue_export(session, grant=grant, actor_id="R-101")
    session.commit()

    _, cancelled = set_consent(
        session, participant_id="P-002", purpose_code="cardio",
        status="withdrawn", actor_id="P-002",
    )
    session.commit()

    assert sorted(cancelled) == [job1.id, job2.id]
    for job_id in cancelled:
        job = session.get(models.ExportJob, job_id)
        assert job.status == "cancelled"
        assert job.cancel_reason == "consent_withdrawn"


def test_withdraw_does_not_touch_other_purposes(session):
    grant = make_grant(session, purpose_code="diabetes", dataset_id="DS-METAB-2024")
    job = queue_export(session, grant=grant, actor_id="R-101")
    session.commit()

    _, cancelled = set_consent(
        session, participant_id="P-005", purpose_code="cardio",
        status="withdrawn", actor_id="P-005",
    )
    session.commit()
    assert cancelled == []
    assert session.get(models.ExportJob, job.id).status == "queued"


def test_withdraw_preserves_access_events(session):
    grant = make_grant(session)
    job = queue_export(session, grant=grant, actor_id="R-101")
    session.commit()
    before = session.query(models.AccessEvent).count()

    set_consent(session, participant_id="P-001", purpose_code="cardio",
                status="withdrawn", actor_id="P-001")
    session.commit()
    after = session.query(models.AccessEvent).count()

    # 历史事件一条不少，只新增（撤回 + 取消导出）
    assert after > before
    queued_events = session.query(models.AccessEvent).filter_by(
        event_type="export_queued", export_job_id=job.id
    ).count()
    assert queued_events == 1

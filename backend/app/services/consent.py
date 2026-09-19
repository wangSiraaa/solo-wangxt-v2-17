"""授权版本管理与撤回。

撤回的三个效果：
1. 追加 withdrawn 版本（历史版本与历史访问事件保持不变）；
2. 立即取消所有"尚未执行"且包含该参与者数据的同用途导出任务；
3. 已发放的下载链接不删除，但每次访问都会重新校验授权而失败。
正在执行中的导出由导出 Worker 的权限检查点在提交前拦截（见 exports.py）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from ..utils import utcnow
from .audit import record_event
from .permissions import current_consent, dataset_participant_ids


def set_consent(
    session: Session,
    *,
    participant_id: str,
    purpose_code: str,
    status: str,
    actor_id: str,
) -> tuple[models.ConsentVersion, list[int]]:
    """写入新版本授权。返回 (新版本, 被取消的导出任务 id 列表)。"""
    assert status in ("granted", "withdrawn")
    last = current_consent(session, participant_id, purpose_code)
    if last is not None and last.status == status:
        return last, []  # 幂等：状态未变化不产生新版本

    version = models.ConsentVersion(
        participant_id=participant_id,
        purpose_code=purpose_code,
        version=(last.version if last else 0) + 1,
        status=status,
    )
    session.add(version)
    session.flush()  # 同事务内的后续查询必须能看到新版本
    record_event(
        session,
        actor_id=actor_id,
        actor_role="participant",
        event_type="consent_withdrawn" if status == "withdrawn" else "consent_granted",
        participant_id=participant_id,
        purpose_code=purpose_code,
        detail={"version": version.version},
    )

    cancelled: list[int] = []
    if status == "withdrawn":
        cancelled = cancel_pending_exports(
            session, participant_id=participant_id, purpose_code=purpose_code
        )
    return version, cancelled


def cancel_pending_exports(
    session: Session, *, participant_id: str, purpose_code: str
) -> list[int]:
    """取消所有 queued 状态、且数据集包含该参与者的同用途导出任务。"""
    jobs = (
        session.query(models.ExportJob)
        .filter_by(status="queued", purpose_code=purpose_code)
        .all()
    )
    cancelled: list[int] = []
    for job in jobs:
        if participant_id not in dataset_participant_ids(session, job.dataset_id):
            continue
        job.status = "cancelled"
        job.cancel_reason = "consent_withdrawn"
        job.finished_at = utcnow()
        record_event(
            session,
            actor_id=participant_id,
            actor_role="participant",
            event_type="export_cancelled",
            export_job_id=job.id,
            grant_id=job.grant_id,
            participant_id=participant_id,
            purpose_code=purpose_code,
            dataset_id=job.dataset_id,
            detail={
                "reasons": ["consent_withdrawn"],
                "withdrawn_participants": [participant_id],
            },
        )
        cancelled.append(job.id)
    return cancelled

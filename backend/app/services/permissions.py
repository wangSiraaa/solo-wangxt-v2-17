"""权限判断引擎：所有数据使用决策的唯一入口。

判定规则（任一不满足即拒绝）：
1. 授权（Grant）未过期；
2. 数据集内每位参与者对该用途的当前授权版本都是 granted。

下载链接访问时额外要求：链接未过期、导出任务已完成。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models
from ..utils import utcnow


@dataclass
class Decision:
    allowed: bool
    reasons: list[str]
    withdrawn_participants: list[str] = field(default_factory=list)


class PermissionDenied(Exception):
    def __init__(self, decision: Decision):
        super().__init__(",".join(decision.reasons))
        self.decision = decision


def current_consent(session: Session, participant_id: str, purpose_code: str):
    """返回 (participant, purpose) 的最新授权版本，无记录则为 None。"""
    return (
        session.query(models.ConsentVersion)
        .filter_by(participant_id=participant_id, purpose_code=purpose_code)
        .order_by(models.ConsentVersion.version.desc())
        .first()
    )


def current_consent_status(
    session: Session, participant_id: str, purpose_code: str
) -> str | None:
    version = current_consent(session, participant_id, purpose_code)
    return version.status if version else None


def dataset_participant_ids(session: Session, dataset_id: str) -> list[str]:
    rows = (
        session.query(models.DatasetRecord.participant_id)
        .filter_by(dataset_id=dataset_id)
        .distinct()
        .all()
    )
    return sorted(r[0] for r in rows)


def withdrawn_participants(
    session: Session, dataset_id: str, purpose_code: str
) -> list[str]:
    """数据集中对该用途当前未授权（撤回或从未授权）的参与者。"""
    return [
        pid
        for pid in dataset_participant_ids(session, dataset_id)
        if current_consent_status(session, pid, purpose_code) != "granted"
    ]


def evaluate_grant(session: Session, grant: models.Grant) -> Decision:
    reasons: list[str] = []
    if grant.expires_at <= utcnow():
        reasons.append("grant_expired")
    withdrawn = withdrawn_participants(session, grant.dataset_id, grant.purpose_code)
    if withdrawn:
        reasons.append("consent_withdrawn")
    return Decision(
        allowed=not reasons, reasons=reasons, withdrawn_participants=withdrawn
    )


def evaluate_download(session: Session, link: models.DownloadLink) -> Decision:
    """下载链接每次访问都走这里重新校验授权。"""
    job = link.export_job
    reasons: list[str] = []
    if link.expires_at <= utcnow():
        reasons.append("link_expired")
    if job.status != "completed":
        reasons.append("export_not_completed")
    grant_decision = evaluate_grant(session, job.grant)
    reasons.extend(grant_decision.reasons)
    return Decision(
        allowed=not reasons,
        reasons=reasons,
        withdrawn_participants=grant_decision.withdrawn_participants,
    )

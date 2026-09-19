from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models


def record_event(
    session: Session,
    *,
    actor_id: str,
    actor_role: str,
    event_type: str,
    request_id: int | None = None,
    grant_id: int | None = None,
    export_job_id: int | None = None,
    participant_id: str | None = None,
    purpose_code: str | None = None,
    dataset_id: str | None = None,
    detail: dict | None = None,
) -> models.AccessEvent:
    """追加一条不可变审计事件。任何流程都不得更新或删除历史事件。"""
    event = models.AccessEvent(
        actor_id=actor_id,
        actor_role=actor_role,
        event_type=event_type,
        request_id=request_id,
        grant_id=grant_id,
        export_job_id=export_job_id,
        participant_id=participant_id,
        purpose_code=purpose_code,
        dataset_id=dataset_id,
        detail=detail,
    )
    session.add(event)
    return event

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_session
from ..deps import Identity, require_role
from ..services.consent import set_consent
from ..services.permissions import current_consent, dataset_participant_ids

router = APIRouter(prefix="/api/participants", tags=["participant"])


@router.get("/me/overview")
def my_overview(
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("participant")),
):
    """参与者门户：每个用途的当前授权状态 + 受影响项目 + 撤回影响预估。"""
    pid = identity.user_id
    my_datasets = set()
    rows = (
        session.query(models.DatasetRecord.dataset_id)
        .filter_by(participant_id=pid)
        .distinct()
        .all()
    )
    for row in rows:
        my_datasets.add(row[0])

    purposes_out = []
    for purpose in session.query(models.Purpose).order_by(models.Purpose.code).all():
        current = current_consent(session, pid, purpose.code)

        # 受影响项目：已批准且数据集包含该参与者、用途匹配的授权
        grants = (
            session.query(models.Grant)
            .filter_by(purpose_code=purpose.code)
            .all()
        )
        projects = []
        queued_exports = 0
        active_links = 0
        for grant in grants:
            if grant.dataset_id not in my_datasets:
                continue
            researcher = session.get(models.Researcher, grant.researcher_id)
            jobs = (
                session.query(models.ExportJob)
                .filter_by(grant_id=grant.id)
                .order_by(models.ExportJob.id)
                .all()
            )
            job_dicts = []
            for job in jobs:
                downloaded = (
                    session.query(models.AccessEvent)
                    .filter_by(event_type="download_served", export_job_id=job.id)
                    .count()
                    > 0
                )
                if job.status == "queued":
                    queued_exports += 1
                if job.status == "completed":
                    active_links += (
                        session.query(models.DownloadLink)
                        .filter_by(export_job_id=job.id)
                        .count()
                    )
                job_dicts.append(
                    {"id": job.id, "status": job.status, "downloaded": downloaded}
                )
            projects.append(
                {
                    "grant_id": grant.id,
                    "project_title": grant.request.project_title,
                    "researcher_name": researcher.name if researcher else grant.researcher_id,
                    "dataset_id": grant.dataset_id,
                    "grant_expires_at": grant.expires_at.isoformat(),
                    "exports": job_dicts,
                }
            )

        purposes_out.append(
            {
                "code": purpose.code,
                "name": purpose.name,
                "description": purpose.description,
                "status": current.status if current else "none",
                "version": current.version if current else 0,
                "updated_at": current.created_at.isoformat() if current else None,
                "datasets": sorted(my_datasets),
                "projects": projects,
                "withdrawal_impact": {
                    "queued_exports": queued_exports,
                    "active_download_links": active_links,
                },
            }
        )
    return {"participant_id": pid, "label": identity.name, "purposes": purposes_out}


class ConsentIn(BaseModel):
    action: str  # "grant" | "withdraw"


@router.post("/me/consents/{purpose_code}")
def change_consent(
    purpose_code: str,
    body: ConsentIn,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("participant")),
):
    if session.get(models.Purpose, purpose_code) is None:
        raise HTTPException(404, f"unknown purpose {purpose_code}")
    if body.action not in ("grant", "withdraw"):
        raise HTTPException(422, "action must be 'grant' or 'withdraw'")
    version, cancelled = set_consent(
        session,
        participant_id=identity.user_id,
        purpose_code=purpose_code,
        status="granted" if body.action == "grant" else "withdrawn",
        actor_id=identity.user_id,
    )
    session.commit()
    return {
        "purpose_code": purpose_code,
        "status": version.status,
        "version": version.version,
        "cancelled_exports": cancelled,
    }


@router.get("/me/events")
def my_events(
    limit: int = 100,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("participant")),
):
    """我的数据访问历史：与我相关的授权事件 + 涉及我所在数据集的访问事件。"""
    pid = identity.user_id
    my_dataset_ids = [
        row[0]
        for row in session.query(models.DatasetRecord.dataset_id)
        .filter_by(participant_id=pid)
        .distinct()
        .all()
    ]
    events = (
        session.query(models.AccessEvent)
        .filter(
            (models.AccessEvent.participant_id == pid)
            | (models.AccessEvent.dataset_id.in_(my_dataset_ids or [""]))
        )
        .order_by(models.AccessEvent.id.desc())
        .limit(min(limit, 500))
        .all()
    )
    return {
        "events": [
            {
                "id": ev.id,
                "actor_id": ev.actor_id,
                "actor_role": ev.actor_role,
                "event_type": ev.event_type,
                "purpose_code": ev.purpose_code,
                "dataset_id": ev.dataset_id,
                "export_job_id": ev.export_job_id,
                "detail": ev.detail,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in events
        ]
    }

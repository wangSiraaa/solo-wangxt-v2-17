from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_session
from ..deps import Identity, require_role
from ..services.audit import record_event
from ..services.exports import queue_export
from ..services.permissions import PermissionDenied

router = APIRouter(prefix="/api", tags=["researcher"])


class RequestIn(BaseModel):
    dataset_id: str
    purpose_code: str
    project_title: str


@router.post("/requests", status_code=201)
def apply_for_access(
    body: RequestIn,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("researcher")),
):
    if session.get(models.Dataset, body.dataset_id) is None:
        raise HTTPException(404, f"unknown dataset {body.dataset_id}")
    if session.get(models.Purpose, body.purpose_code) is None:
        raise HTTPException(404, f"unknown purpose {body.purpose_code}")
    req = models.AccessRequest(
        researcher_id=identity.user_id,
        project_title=body.project_title,
        dataset_id=body.dataset_id,
        purpose_code=body.purpose_code,
    )
    session.add(req)
    session.flush()
    record_event(
        session,
        actor_id=identity.user_id,
        actor_role="researcher",
        event_type="request_submitted",
        request_id=req.id,
        purpose_code=req.purpose_code,
        dataset_id=req.dataset_id,
        detail={"project_title": req.project_title},
    )
    session.commit()
    return {"id": req.id, "status": req.status}


def _request_dict(session: Session, req: models.AccessRequest) -> dict:
    grant = req.grant
    return {
        "id": req.id,
        "researcher_id": req.researcher_id,
        "project_title": req.project_title,
        "dataset_id": req.dataset_id,
        "purpose_code": req.purpose_code,
        "status": req.status,
        "created_at": req.created_at.isoformat(),
        "decision_note": req.decision_note,
        "grant": (
            {
                "id": grant.id,
                "expires_at": grant.expires_at.isoformat(),
                "granted_by": grant.granted_by,
            }
            if grant
            else None
        ),
    }


@router.get("/requests/mine")
def my_requests(
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("researcher")),
):
    reqs = (
        session.query(models.AccessRequest)
        .filter_by(researcher_id=identity.user_id)
        .order_by(models.AccessRequest.id.desc())
        .all()
    )
    return {"requests": [_request_dict(session, r) for r in reqs]}


class ExportIn(BaseModel):
    grant_id: int


@router.post("/exports", status_code=201)
def request_export(
    body: ExportIn,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("researcher")),
):
    grant = session.get(models.Grant, body.grant_id)
    if grant is None or grant.researcher_id != identity.user_id:
        raise HTTPException(404, "grant not found")
    try:
        job = queue_export(session, grant=grant, actor_id=identity.user_id)
    except PermissionDenied as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "export_denied",
                "reasons": exc.decision.reasons,
                "withdrawn_participants": exc.decision.withdrawn_participants,
            },
        )
    session.commit()
    return {"id": job.id, "status": job.status}


@router.get("/exports/mine")
def my_exports(
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("researcher")),
):
    jobs = (
        session.query(models.ExportJob)
        .filter_by(researcher_id=identity.user_id)
        .order_by(models.ExportJob.id.desc())
        .all()
    )
    out = []
    for job in jobs:
        link = (
            session.query(models.DownloadLink)
            .filter_by(export_job_id=job.id)
            .order_by(models.DownloadLink.created_at.desc())
            .first()
        )
        downloaded = (
            session.query(models.AccessEvent)
            .filter_by(event_type="download_served", export_job_id=job.id)
            .count()
            > 0
        )
        out.append(
            {
                "id": job.id,
                "grant_id": job.grant_id,
                "dataset_id": job.dataset_id,
                "purpose_code": job.purpose_code,
                "status": job.status,
                "cancel_reason": job.cancel_reason,
                "row_count": job.row_count,
                "created_at": job.created_at.isoformat(),
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "downloaded": downloaded,
                "download_token": link.token if link else None,
                "link_expires_at": link.expires_at.isoformat() if link else None,
            }
        )
    return {"exports": out}

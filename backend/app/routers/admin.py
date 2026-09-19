from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import SessionLocal, get_session
from ..deps import Identity, require_role
from ..services.audit import record_event
from ..services.exports import run_pending_exports
from ..utils import utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _event_dict(ev: models.AccessEvent) -> dict:
    return {
        "id": ev.id,
        "actor_id": ev.actor_id,
        "actor_role": ev.actor_role,
        "event_type": ev.event_type,
        "request_id": ev.request_id,
        "grant_id": ev.grant_id,
        "export_job_id": ev.export_job_id,
        "participant_id": ev.participant_id,
        "purpose_code": ev.purpose_code,
        "dataset_id": ev.dataset_id,
        "detail": ev.detail,
        "created_at": ev.created_at.isoformat(),
    }


@router.get("/requests")
def list_requests(
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("admin")),
):
    reqs = (
        session.query(models.AccessRequest)
        .order_by(models.AccessRequest.id.desc())
        .all()
    )
    out = []
    for req in reqs:
        researcher = session.get(models.Researcher, req.researcher_id)
        out.append(
            {
                "id": req.id,
                "researcher_id": req.researcher_id,
                "researcher_name": researcher.name if researcher else req.researcher_id,
                "project_title": req.project_title,
                "dataset_id": req.dataset_id,
                "purpose_code": req.purpose_code,
                "status": req.status,
                "created_at": req.created_at.isoformat(),
                "decision_note": req.decision_note,
                "grant": (
                    {
                        "id": req.grant.id,
                        "expires_at": req.grant.expires_at.isoformat(),
                    }
                    if req.grant
                    else None
                ),
            }
        )
    return {"requests": out}


class ApproveIn(BaseModel):
    days_valid: int = 7


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    body: ApproveIn,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("admin")),
):
    req = session.get(models.AccessRequest, request_id)
    if req is None:
        raise HTTPException(404, "request not found")
    if req.status != "pending":
        raise HTTPException(409, f"request already {req.status}")
    req.status = "approved"
    req.decided_at = utcnow()
    req.decided_by = identity.user_id
    grant = models.Grant(
        request_id=req.id,
        researcher_id=req.researcher_id,
        dataset_id=req.dataset_id,
        purpose_code=req.purpose_code,
        granted_by=identity.user_id,
        expires_at=utcnow() + timedelta(days=body.days_valid),
    )
    session.add(grant)
    session.flush()
    record_event(
        session,
        actor_id=identity.user_id,
        actor_role="admin",
        event_type="request_approved",
        request_id=req.id,
        grant_id=grant.id,
        purpose_code=req.purpose_code,
        dataset_id=req.dataset_id,
        detail={"days_valid": body.days_valid},
    )
    session.commit()
    return {"request_id": req.id, "grant_id": grant.id, "expires_at": grant.expires_at.isoformat()}


class DenyIn(BaseModel):
    note: str = ""


@router.post("/requests/{request_id}/deny")
def deny_request(
    request_id: int,
    body: DenyIn,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("admin")),
):
    req = session.get(models.AccessRequest, request_id)
    if req is None:
        raise HTTPException(404, "request not found")
    if req.status != "pending":
        raise HTTPException(409, f"request already {req.status}")
    req.status = "denied"
    req.decided_at = utcnow()
    req.decided_by = identity.user_id
    req.decision_note = body.note
    record_event(
        session,
        actor_id=identity.user_id,
        actor_role="admin",
        event_type="request_denied",
        request_id=req.id,
        purpose_code=req.purpose_code,
        dataset_id=req.dataset_id,
        detail={"note": body.note},
    )
    session.commit()
    return {"request_id": req.id, "status": req.status}


@router.get("/events")
def list_events(
    limit: int = 100,
    session: Session = Depends(get_session),
    identity: Identity = Depends(require_role("admin")),
):
    events = (
        session.query(models.AccessEvent)
        .order_by(models.AccessEvent.id.desc())
        .limit(min(limit, 500))
        .all()
    )
    return {"events": [_event_dict(ev) for ev in events]}


@router.post("/worker/run")
def run_worker(identity: Identity = Depends(require_role("admin"))):
    """手动触发导出 Worker（演示与测试用；后台 Worker 也会自动轮询）。"""
    results = run_pending_exports(SessionLocal)
    return {"processed": [{"id": job_id, "status": status} for job_id, status in results]}

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_session
from ..services.audit import record_event
from ..services.permissions import evaluate_download

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


def _get_link(session: Session, token: str) -> models.DownloadLink:
    link = session.get(models.DownloadLink, token)
    if link is None:
        raise HTTPException(404, "unknown download token")
    return link


@router.get("/{token}/check")
def check_download(token: str, session: Session = Depends(get_session)):
    """前端"校验链接"按钮：返回当前授权校验结果，不产生下载事件。"""
    link = _get_link(session, token)
    decision = evaluate_download(session, link)
    return {
        "valid": decision.allowed,
        "reasons": decision.reasons,
        "withdrawn_participants": decision.withdrawn_participants,
        "expires_at": link.expires_at.isoformat(),
    }


@router.get("/{token}")
def download(token: str, session: Session = Depends(get_session)):
    """下载入口：每次访问都重新校验授权，拒绝与成功都记入审计。"""
    link = _get_link(session, token)
    job = link.export_job
    decision = evaluate_download(session, link)
    if not decision.allowed:
        record_event(
            session,
            actor_id=job.researcher_id,
            actor_role="researcher",
            event_type="download_denied",
            export_job_id=job.id,
            grant_id=job.grant_id,
            purpose_code=job.purpose_code,
            dataset_id=job.dataset_id,
            detail={
                "reasons": decision.reasons,
                "withdrawn_participants": decision.withdrawn_participants,
            },
        )
        session.commit()
        raise HTTPException(
            status_code=403,
            detail={
                "error": "download_denied",
                "reasons": decision.reasons,
                "withdrawn_participants": decision.withdrawn_participants,
            },
        )
    record_event(
        session,
        actor_id=job.researcher_id,
        actor_role="researcher",
        event_type="download_served",
        export_job_id=job.id,
        grant_id=job.grant_id,
        purpose_code=job.purpose_code,
        dataset_id=job.dataset_id,
    )
    session.commit()
    return FileResponse(
        job.file_path,
        media_type="text/csv",
        filename=f"{job.dataset_id}-export-{job.id}.csv",
    )

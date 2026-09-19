from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import Actor, current_actor, log_event, require_role
from ..config import get_settings
from ..db import get_conn

router = APIRouter(tags=["admin"], prefix="/api/admin")


class DecisionIn(BaseModel):
    approve: bool
    reviewer_note: str = ""
    grant_minutes: int | None = None  # 为空时使用默认窗口


@router.get("/requests")
def list_requests(status: str | None = None, actor: Actor = Depends(current_actor)):
    require_role(actor, "admin")
    sql = """
        SELECT r.*, d.title AS dataset_title, d.code AS dataset_code,
               pu.title AS purpose_title, pu.code AS purpose_code,
               res.code AS researcher_code, res.display_name AS researcher_name,
               (r.grant_expires_at IS NOT NULL AND r.grant_expires_at > now()) AS grant_active
          FROM access_requests r
          JOIN datasets d ON d.id=r.dataset_id
          JOIN purposes pu ON pu.id=r.purpose_id
          JOIN researchers res ON res.id=r.researcher_id
    """
    params: tuple = ()
    if status:
        sql += " WHERE r.status=%s"
        params = (status,)
    sql += " ORDER BY r.submitted_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.post("/requests/{request_id}/decision")
def decide(request_id: int, body: DecisionIn, actor: Actor = Depends(current_actor)):
    """按用途授予限时下载权限。批准只开通“限时窗口”，不改变参与者的授权状态。"""
    require_role(actor, "admin")
    settings = get_settings()
    with get_conn() as conn:
        req = conn.execute(
            "SELECT * FROM access_requests WHERE id=%s FOR UPDATE", (request_id,)
        ).fetchone()
        if not req:
            raise HTTPException(404, "申请不存在")
        if req["status"] != "pending":
            raise HTTPException(409, f"申请已被处理：{req['status']}")

        if body.approve:
            minutes = body.grant_minutes or settings.default_grant_minutes
            row = conn.execute(
                """UPDATE access_requests SET status='approved', decided_at=now(),
                      decided_by=%s, grant_expires_at=now() + (%s || ' minutes')::interval,
                      reviewer_note=%s, updated_at=now()
                    WHERE id=%s RETURNING *""",
                (actor.admin_id, minutes, body.reviewer_note, request_id),
            ).fetchone()
            action = "request_approved"
            detail = {"grant_minutes": minutes}
        else:
            row = conn.execute(
                """UPDATE access_requests SET status='rejected', decided_at=now(),
                      decided_by=%s, reviewer_note=%s, grant_expires_at=NULL,
                      updated_at=now()
                    WHERE id=%s RETURNING *""",
                (actor.admin_id, body.reviewer_note, request_id),
            ).fetchone()
            action = "request_rejected"
            detail = {"note": body.reviewer_note}

        log_event(conn, actor_identity_id=actor.identity_id, action=action,
                  request_id=request_id, detail=detail)
    return dict(row)


@router.get("/jobs")
def list_jobs(actor: Actor = Depends(current_actor)):
    """导出队列监控：queued/running/cancelled/complete 全量。"""
    require_role(actor, "admin")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT j.*, r.researcher_id, r.purpose_id, r.dataset_id,
                      res.code AS researcher_code, d.code AS dataset_code,
                      pu.code AS purpose_code
                 FROM export_jobs j
                 JOIN access_requests r ON r.id=j.request_id
                 JOIN datasets d ON d.id=r.dataset_id
                 JOIN purposes pu ON pu.id=r.purpose_id
                 JOIN researchers res ON res.id=r.researcher_id
                ORDER BY j.requested_at DESC LIMIT 100"""
        ).fetchall()
    return [dict(r) for r in rows]

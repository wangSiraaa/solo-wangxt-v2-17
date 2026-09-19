from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import Actor, current_actor, log_event, require_role
from ..consents import check_request_usable
from ..db import get_conn

router = APIRouter(tags=["researcher"], prefix="/api/researcher")


class SubmitRequestIn(BaseModel):
    dataset_id: int
    purpose_id: int
    justification: str = Field(default="", max_length=2000)


@router.post("/requests")
def submit_request(body: SubmitRequestIn, actor: Actor = Depends(current_actor)):
    require_role(actor, "researcher")
    with get_conn() as conn:
        exists = conn.execute(
            """SELECT id, status FROM access_requests
                WHERE researcher_id=%s AND dataset_id=%s AND purpose_id=%s""",
            (actor.researcher_id, body.dataset_id, body.purpose_id),
        ).fetchone()
        if exists:
            if exists["status"] == "pending":
                raise HTTPException(409, "该数据集 × 用途的申请正在审批中")
            if exists["status"] == "rejected":
                # 拒绝后允许重新提交：复用同一行回到 pending
                row = conn.execute(
                    """UPDATE access_requests SET status='pending', justification=%s,
                          submitted_at=now(), decided_at=NULL, decided_by=NULL,
                          grant_expires_at=NULL, reviewer_note='', updated_at=now()
                        WHERE id=%s RETURNING *""",
                    (body.justification, exists["id"]),
                ).fetchone()
            else:
                raise HTTPException(409, "该数据集 × 用途已有获批申请，请到“我的项目”查看")
        else:
            row = conn.execute(
                """INSERT INTO access_requests (researcher_id, dataset_id, purpose_id, justification)
                   VALUES (%s,%s,%s,%s) RETURNING *""",
                (actor.researcher_id, body.dataset_id, body.purpose_id, body.justification),
            ).fetchone()
        log_event(conn, actor_identity_id=actor.identity_id, action="request_submitted",
                  request_id=row["id"],
                  detail={"dataset_id": body.dataset_id, "purpose_id": body.purpose_id})
    return dict(row)


def _fetch_project_detail(conn, request_id: int) -> dict:
    req = conn.execute(
        """SELECT r.*, d.title AS dataset_title, d.code AS dataset_code,
                  pu.title AS purpose_title, pu.code AS purpose_code,
                  (r.grant_expires_at IS NOT NULL AND r.grant_expires_at > now()) AS grant_active
             FROM access_requests r
             JOIN datasets d ON d.id=r.dataset_id
             JOIN purposes pu ON pu.id=r.purpose_id
            WHERE r.id=%s""",
        (request_id,),
    ).fetchone()
    if not req:
        raise HTTPException(404, "申请不存在")
    jobs = conn.execute(
        """SELECT j.*,
                 (SELECT token FROM download_links l WHERE l.export_id=j.id
                    AND l.revoked=FALSE AND l.expires_at>now() LIMIT 1) AS active_token,
                 (SELECT count(*) FROM download_links l WHERE l.export_id=j.id) AS links_total,
                 (SELECT count(*) FROM download_links l WHERE l.export_id=j.id AND l.revoked) AS links_revoked,
                 (SELECT count(*) FROM download_links l WHERE l.export_id=j.id AND l.access_count>0) AS links_used
            FROM export_jobs j WHERE j.request_id=%s ORDER BY j.requested_at""",
        (request_id,),
    ).fetchall()
    req = dict(req)
    req["jobs"] = [dict(j) for j in jobs]
    return req


@router.get("/projects")
def my_projects(actor: Actor = Depends(current_actor)):
    """研究员视角：自己的申请、授权窗口、导出任务、已下载/可下载状态。"""
    require_role(actor, "researcher")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.id, r.status, r.justification, r.submitted_at, r.decided_at,
                      r.grant_expires_at, r.reviewer_note,
                      d.id AS dataset_id, d.code AS dataset_code, d.title AS dataset_title,
                      pu.id AS purpose_id, pu.code AS purpose_code, pu.title AS purpose_title,
                      (r.grant_expires_at IS NOT NULL AND r.grant_expires_at > now()) AS grant_active,
                      (SELECT count(*) FROM export_jobs j WHERE j.request_id=r.id) AS job_count,
                      (SELECT count(*) FROM export_jobs j WHERE j.request_id=r.id
                         AND j.status IN ('queued','running')) AS pending_count,
                      (SELECT count(*) FROM export_jobs j WHERE j.request_id=r.id
                         AND j.status='complete') AS complete_count,
                      (SELECT count(*) FROM export_jobs j WHERE j.request_id=r.id
                         AND j.status='cancelled') AS cancelled_count
                 FROM access_requests r
                 JOIN datasets d ON d.id=r.dataset_id
                 JOIN purposes pu ON pu.id=r.purpose_id
                WHERE r.researcher_id=%s
                ORDER BY r.submitted_at DESC""",
            (actor.researcher_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/projects/{request_id}")
def project_detail(request_id: int, actor: Actor = Depends(current_actor)):
    require_role(actor, "researcher")
    with get_conn() as conn:
        req = conn.execute(
            "SELECT researcher_id FROM access_requests WHERE id=%s", (request_id,)
        ).fetchone()
        if not req:
            raise HTTPException(404, "申请不存在")
        if req["researcher_id"] != actor.researcher_id:
            raise HTTPException(403, "不能查看他人项目")
        detail = _fetch_project_detail(conn, request_id)
    return detail


@router.post("/projects/{request_id}/exports")
def queue_export(request_id: int, actor: Actor = Depends(current_actor)):
    """CP-1：导出入队检查点。"""
    require_role(actor, "researcher")
    denial: str | None = None
    queued_row = None
    with get_conn() as conn:
        request_row = conn.execute(
            "SELECT * FROM access_requests WHERE id=%s", (request_id,)
        ).fetchone()
        if not request_row or request_row["researcher_id"] != actor.researcher_id:
            raise HTTPException(404, "申请不存在或不属于当前研究员")

        # 入队前同步检查；worker 写文件前还会有 CP-2，下载时还有 CP-4
        denial = check_request_usable(conn, request_row)
        if denial:
            # 拒绝事件与异常分离：先提交审计，再在事务外返回 409
            log_event(conn, actor_identity_id=actor.identity_id, action="download_denied",
                      request_id=request_id,
                      detail={"checkpoint": "CP-1", "reason": denial})
        else:
            queued_row = conn.execute(
                """INSERT INTO export_jobs (request_id, status) VALUES (%s,'queued') RETURNING *""",
                (request_id,),
            ).fetchone()
            log_event(conn, actor_identity_id=actor.identity_id, action="export_queued",
                      request_id=request_id, export_id=queued_row["id"],
                      detail={"checkpoint": "CP-1"})

    if denial:
        detail_map = {
            "request_not_approved": "申请尚未获批，不能导出",
            "grant_expired": "限时下载窗口已过期，请重新申请",
            "participant_withdrew": "已有参与者撤回该用途授权，导出已被拦截",
        }
        raise HTTPException(409, {"reason": denial, "message": detail_map.get(denial, denial)})
    return dict(queued_row)

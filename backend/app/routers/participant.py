from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import Actor, current_actor
from ..consents import regrant_consent, withdraw_consent
from ..db import get_conn

router = APIRouter(tags=["participant"], prefix="/api/participant")


@router.get("/consents")
def my_consents(actor: Actor = Depends(current_actor)):
    """参与者视角：每类用途的当前授权状态 + 版本历史。"""
    if actor.role != "participant":
        raise HTTPException(403, "仅参与者可查看自己的授权")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.id AS consent_id, c.version, c.status, c.granted_at,
                      c.withdrawn_at, c.withdraw_reason,
                      pu.id AS purpose_id, pu.code AS purpose_code,
                      pu.title AS purpose_title, pu.description AS purpose_description,
                      (SELECT count(*) FROM consent_events e WHERE e.consent_id=c.id) AS event_count
                 FROM consents c JOIN purposes pu ON pu.id=c.purpose_id
                WHERE c.participant_id=%s ORDER BY pu.id""",
            (actor.participant_id,),
        ).fetchall()
        result = []
        for r in rows:
            events = conn.execute(
                """SELECT e.version, e.action, e.reason, e.occurred_at, i.label AS actor_label
                     FROM consent_events e LEFT JOIN identities i ON i.id=e.actor_identity_id
                    WHERE e.consent_id=%s ORDER BY e.version DESC""",
                (r["consent_id"],),
            ).fetchall()
            item = dict(r)
            item["history"] = [dict(e) for e in events]
            result.append(item)
    return result


@router.get("/affected-projects")
def affected_projects(purpose_id: int | None = None, actor: Actor = Depends(current_actor)):
    """撤回将影响/已影响哪些研究项目与导出任务。

    范围：所有申请了“包含本人记录的数据集”且用途相同的项目，
    以及它们名下的导出任务和下载链接。用于撤回前确认范围、撤回后核对结果。
    """
    if actor.role != "participant":
        raise HTTPException(403, "仅参与者可查看受影响项目")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.id AS request_id, r.status AS request_status,
                      r.grant_expires_at,
                      (r.grant_expires_at IS NOT NULL AND r.grant_expires_at>now()) AS grant_active,
                      pu.id AS purpose_id, pu.code AS purpose_code, pu.title AS purpose_title,
                      d.id AS dataset_id, d.code AS dataset_code, d.title AS dataset_title,
                      res.code AS researcher_code, res.display_name AS researcher_name,
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
                 JOIN researchers res ON res.id=r.researcher_id
                WHERE r.purpose_id = COALESCE(%s, r.purpose_id)
                  AND d.id IN (SELECT dataset_id FROM dataset_records WHERE participant_id=%s)
                ORDER BY r.submitted_at DESC""",
            (purpose_id, actor.participant_id),
        ).fetchall()
        projects = []
        for r in rows:
            jobs = conn.execute(
                """SELECT j.id, j.status, j.requested_at, j.started_at, j.finished_at,
                          j.denial_reason, j.record_count,
                          (SELECT count(*) FROM download_links l WHERE l.export_id=j.id) AS links_total,
                          (SELECT count(*) FROM download_links l WHERE l.export_id=j.id AND l.revoked) AS links_revoked,
                          (SELECT count(*) FROM download_links l WHERE l.export_id=j.id AND l.access_count>0) AS links_used
                     FROM export_jobs j WHERE j.request_id=%s ORDER BY j.requested_at""",
                (r["request_id"],),
            ).fetchall()
            item = dict(r)
            item["jobs"] = [dict(j) for j in jobs]
            projects.append(item)
    return projects


class WithdrawIn(BaseModel):
    purpose_id: int
    reason: str = Field(default="", max_length=1000)


@router.post("/consents/withdraw")
def withdraw(body: WithdrawIn, actor: Actor = Depends(current_actor)):
    """参与者独立撤回入口。返回被连带取消的导出任务，便于前端即时反馈。"""
    if actor.role != "participant":
        raise HTTPException(403, "仅参与者可撤回授权")
    with get_conn() as conn:
        try:
            result = withdraw_consent(
                conn,
                participant_id=actor.participant_id,
                purpose_id=body.purpose_id,
                actor_identity_id=actor.identity_id,
                reason=body.reason,
            )
        except ValueError as e:
            raise HTTPException(409, str(e))
    return {
        "status": "withdrawn",
        "version": result["consent"]["version"],
        "cancelled_export_ids": result["cancelled_export_ids"],
        "revoked_link_ids": result["revoked_link_ids"],
        "message": "授权已撤回；未完成导出已取消，历史访问记录保留，已发下载链接已撤销并会在访问时重新校验。",
    }


class RegrantIn(BaseModel):
    purpose_id: int


@router.post("/consents/regrant")
def regrant(body: RegrantIn, actor: Actor = Depends(current_actor)):
    if actor.role != "participant":
        raise HTTPException(403, "仅参与者可重新授予授权")
    with get_conn() as conn:
        try:
            updated = regrant_consent(
                conn,
                participant_id=actor.participant_id,
                purpose_id=body.purpose_id,
                actor_identity_id=actor.identity_id,
            )
        except ValueError as e:
            raise HTTPException(409, str(e))
    return dict(updated)

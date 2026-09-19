import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..auth import Actor, current_actor, log_event, require_role
from ..consents import effective_grants, is_grant_effective, list_dataset_participants, lock_slots
from ..db import get_conn

router = APIRouter(tags=["downloads"])


@router.get("/api/researcher/downloads/{token}")
def download_link(token: str, actor: Actor = Depends(current_actor)):
    """CP-4：下载链接每次访问都重新校验。

    校验顺序：
      1. 链接存在、属于该研究员的项目、未被撤销、未过期；
      2. 导出任务 complete；
      3. 授权窗口仍有效（管理员授予的限时窗口）；
      4. 数据集中所有参与者对该用途的授权仍为 granted（持锁读取）。
    任一不满足即拒绝并记 access_events('download_denied')；历史记录不删除。
    """
    require_role(actor, "researcher")
    denial: dict | None = None
    file_path = filename = None
    response_headers: dict = {}

    with get_conn() as conn:
        link = conn.execute(
            """SELECT l.* FROM download_links l
                JOIN export_jobs j ON j.id=l.export_id
                JOIN access_requests r ON r.id=j.request_id
               WHERE l.token=%s AND r.researcher_id=%s""",
            (token, actor.researcher_id),
        ).fetchone()
        if link is None:
            # 链接归属都无法确认，无法关联到具体行记录；返回 404
            raise HTTPException(404, "下载链接不存在或不属于当前研究员")

        job = conn.execute("SELECT * FROM export_jobs WHERE id=%s", (link["export_id"],)).fetchone()
        req = conn.execute("SELECT * FROM access_requests WHERE id=%s", (job["request_id"],)).fetchone()

        def fail(reason: str, message: str) -> None:
            # 在当前事务内落地拒绝事件；异常在事务提交后再抛出，避免回滚掉审计记录
            log_event(conn, actor_identity_id=actor.identity_id, action="download_denied",
                      request_id=req["id"], export_id=job["id"], link_id=link["id"],
                      detail={"checkpoint": "CP-4", "reason": reason})
            denial["code"] = reason
            denial["message"] = message  # type: ignore[index]

        denial = {"code": None, "message": None}

        if link["revoked"]:
            fail("link_revoked", "该下载链接已因参与者撤回授权而失效")
        elif job["status"] != "complete":
            fail("export_not_complete", f"导出任务状态为 {job['status']}，没有可下载文件")
        elif req["grant_expires_at"] is None:
            fail("grant_expired", "管理员授予的限时访问已结束")
        else:
            # CP-4 的核心：重新锁定授权位并逐人校验当前状态（而非只看导出时快照）
            participant_ids = list_dataset_participants(conn, req["dataset_id"])
            lock_slots(conn, participant_ids, req["purpose_id"])
            grants = effective_grants(conn, participant_ids, req["purpose_id"])
            withdrew = [pid for pid in participant_ids if not is_grant_effective(grants.get(pid))]

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            if link["expires_at"] <= now or req["grant_expires_at"] <= now:
                fail("grant_expired", "限时下载窗口已过期")
            elif withdrew:
                fail("participant_withdrew",
                     f"已有 {len(withdrew)} 位参与者撤回该用途授权，链接已失效，不能下载")
            elif not job["file_path"] or not os.path.exists(job["file_path"]):
                fail("file_missing", "导出文件不存在")

        if denial["code"] is None:
            conn.execute(
                """UPDATE download_links SET access_count=access_count+1, last_accessed_at=now()
                    WHERE id=%s""",
                (link["id"],),
            )
            log_event(conn, actor_identity_id=actor.identity_id, action="download",
                      request_id=req["id"], export_id=job["id"], link_id=link["id"],
                      detail={"checkpoint": "CP-4", "record_count": job["record_count"]})
            file_path = job["file_path"]
            filename = os.path.basename(job["file_path"])
            from datetime import datetime, timezone
            response_headers = {
                "X-Consent-Revalidated-At": datetime.now(timezone.utc).isoformat(),
                "X-Export-Id": str(job["id"]),
                "X-Sha256": job["file_sha256"] or "",
            }

    # 事务已提交：再抛出拒绝（审计事件不会被回滚）
    if denial["code"] is not None:
        raise HTTPException(409, {"reason": denial["code"], "message": denial["message"]})

    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=filename,
        headers=response_headers,
    )


@router.get("/api/events")
def list_events(limit: int = 50, actor: Actor = Depends(current_actor)):
    """访问事件流（只追加日志）。管理员看全部，其他身份看与自己相关的。"""
    limit = min(limit, 300)
    sql = """
        SELECT e.*, i.label AS actor_label, i.role AS actor_role,
               r.id AS request_ref,
               (SELECT code FROM datasets WHERE id=r.dataset_id) AS dataset_code,
               (SELECT code FROM purposes WHERE id=r.purpose_id) AS purpose_code
          FROM access_events e
          LEFT JOIN identities i ON i.id=e.actor_identity_id
          LEFT JOIN access_requests r ON r.id=e.request_id
    """
    where, params = "", []
    if actor.role == "researcher":
        where = " WHERE (r.researcher_id = %s OR e.actor_identity_id = %s)"
        params = [actor.researcher_id, actor.identity_id]
    elif actor.role == "participant":
        # 参与者：本人的授权事件 + 涉及本人数据所在数据集的导出与下载事件
        where = """ WHERE e.actor_identity_id = %s
                    OR (r.id IS NOT NULL AND EXISTS (
                        SELECT 1 FROM dataset_records dr
                         WHERE dr.dataset_id = r.dataset_id
                           AND dr.participant_id = %s
                    ))
        """
        params = [actor.identity_id, actor.participant_id]
    sql += where + " ORDER BY e.occurred_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

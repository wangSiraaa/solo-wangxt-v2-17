"""授权判断与撤回的核心事务逻辑。

并发模型（关键设计）：
- consent_slots 为每位“参与者 × 用途”预置一行锁位。
- 所有会改变授权/导出状态的事务统一按“先锁 consent_slots，再写 export_jobs”
  的顺序加锁，避免撤回事务与导出/下载事务互相绕过。

三个权限检查点：
  CP-1 导出入队：申请必须 approved 且在限时窗口内，且当时存在有效授予。
  CP-2 导出执行：worker 生成文件前重新校验，若参与者已撤回（或窗口过期）
                则任务置为 cancelled，不生成文件。
  CP-3 撤回生效：撤回事务在持锁期间把该参与者该用途下
                queued/running 的导出任务批量取消，并撤销其已发链接。
  CP-4 链接访问：下载链接每次访问都重新校验授权（授予未撤回 + 窗口未过期），
                不因为“文件已生成”而放行。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg

from .auth import log_event
from .config import get_settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lock_slots(conn: psycopg.Connection, participant_ids: list[int], purpose_id: int) -> None:
    """按确定顺序锁定 (participant, purpose) 授权位，避免死锁。"""
    if not participant_ids:
        return
    ordered = sorted(set(participant_ids))
    conn.execute(
        """SELECT participant_id, purpose_id FROM consent_slots
           WHERE purpose_id = %s AND participant_id = ANY(%s)
           ORDER BY participant_id FOR UPDATE""",
        (purpose_id, ordered),
    )


def effective_grants(conn: psycopg.Connection, participant_ids: list[int], purpose_id: int) -> dict[int, dict]:
    """读取给定参与者在某用途下的当前授权状态（调用方需已锁定 slots 或只读用途）。"""
    if not participant_ids:
        return {}
    rows = conn.execute(
        """SELECT c.participant_id, c.id AS consent_id, c.version, c.status,
                  c.granted_at, c.withdrawn_at
             FROM consents c
            WHERE c.purpose_id = %s AND c.participant_id = ANY(%s)""",
        (purpose_id, sorted(set(participant_ids))),
    ).fetchall()
    return {r["participant_id"]: r for r in rows}


def list_dataset_participants(conn: psycopg.Connection, dataset_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT participant_id FROM dataset_records WHERE dataset_id = %s ORDER BY 1",
        (dataset_id,),
    ).fetchall()
    return [r["participant_id"] for r in rows]


def is_grant_effective(grant: Optional[dict], at: Optional[datetime] = None) -> bool:
    """单个授权当前是否有效：存在、状态 granted 且未撤回。"""
    at = at or _now()
    if not grant or grant["status"] != "granted":
        return False
    if grant.get("withdrawn_at") and grant["withdrawn_at"] <= at:
        return False
    return True


# ---------- CP-3：撤回 ----------
def withdraw_consent(
    conn: psycopg.Connection,
    *,
    participant_id: int,
    purpose_id: int,
    actor_identity_id: int,
    reason: str,
) -> dict:
    """在调用方事务内执行撤回：版本升级 + 取消未完成导出 + 撤销链接 + 事件。

    历史访问记录（access_events / 已完成导出）一律不删除。
    """
    lock_slots(conn, [participant_id], purpose_id)

    consent = conn.execute(
        "SELECT * FROM consents WHERE participant_id=%s AND purpose_id=%s FOR UPDATE",
        (participant_id, purpose_id),
    ).fetchone()
    if consent is None:
        raise ValueError("该参与者对此用途没有授权记录")
    if consent["status"] == "withdrawn":
        raise ValueError("授权已处于撤回状态，无需重复撤回")

    next_version = consent["version"] + 1
    updated = conn.execute(
        """UPDATE consents
              SET version=%s, status='withdrawn', withdrawn_at=now(), withdraw_reason=%s
            WHERE id=%s RETURNING *""",
        (next_version, reason, consent["id"]),
    ).fetchone()

    conn.execute(
        """INSERT INTO consent_events (consent_id, version, action, actor_identity_id, reason)
           VALUES (%s,%s,'withdrawn',%s,%s)""",
        (consent["id"], next_version, actor_identity_id, reason),
    )

    # CP-3：取消该参与者该用途下所有 queued / running 的导出任务。
    # 导出任务面向“整份数据集”，只要其中任一数据主体撤回，未完成任务即不得产出文件。
    cancelled_rows = conn.execute(
        """UPDATE export_jobs e
              SET status='cancelled', finished_at=now(),
                  denial_reason = COALESCE(NULLIF(e.denial_reason,''),
                                           'participant_withdrew')
             FROM access_requests r
            WHERE e.request_id = r.id
              AND r.purpose_id = %s
              AND r.dataset_id IN (
                  SELECT dataset_id FROM dataset_records WHERE participant_id = %s
              )
              AND e.status IN ('queued','running')
          RETURNING e.id""",
        (purpose_id, participant_id),
    ).fetchall()
    cancelled_ids = [r["id"] for r in cancelled_rows]

    # 已完成的导出不删除文件、不改历史，但撤销其全部未撤销的下载链接，
    # 使“再次访问必须重新校验授权”落到实处（CP-4 也会在服务端再次拦截）。
    revoked_links = conn.execute(
        """UPDATE download_links l
              SET revoked = TRUE
             FROM export_jobs e
             JOIN access_requests r ON r.id = e.request_id
            WHERE l.export_id = e.id
              AND l.revoked = FALSE
              AND r.purpose_id = %s
              AND r.dataset_id IN (
                  SELECT dataset_id FROM dataset_records WHERE participant_id = %s
              )
          RETURNING l.id, l.export_id""",
        (purpose_id, participant_id),
    ).fetchall()
    revoked_link_ids = [r["id"] for r in revoked_links]

    for eid in cancelled_ids:
        log_event(conn, actor_identity_id=actor_identity_id, action="export_cancelled",
                  export_id=eid, consent_id=consent["id"],
                  detail={"checkpoint": "CP-3", "reason": "participant_withdrew",
                          "participant_id": participant_id, "purpose_id": purpose_id})
    if revoked_link_ids:
        log_event(conn, actor_identity_id=actor_identity_id, action="link_revoked",
                  consent_id=consent["id"],
                  detail={"checkpoint": "CP-3", "link_ids": revoked_link_ids,
                          "participant_id": participant_id, "purpose_id": purpose_id})

    log_event(conn, actor_identity_id=actor_identity_id, action="consent_withdrawn",
              consent_id=consent["id"],
              detail={"participant_id": participant_id, "purpose_id": purpose_id,
                      "version": next_version, "cancelled_export_ids": cancelled_ids,
                      "revoked_link_ids": revoked_link_ids, "reason": reason})

    return {"consent": updated,
            "cancelled_export_ids": cancelled_ids,
            "revoked_link_ids": revoked_link_ids}


def regrant_consent(
    conn: psycopg.Connection,
    *,
    participant_id: int,
    purpose_id: int,
    actor_identity_id: int,
) -> dict:
    """参与者重新授予（可选演示流程）：新建版本；已取消任务不会自动恢复。"""
    lock_slots(conn, [participant_id], purpose_id)
    consent = conn.execute(
        "SELECT * FROM consents WHERE participant_id=%s AND purpose_id=%s FOR UPDATE",
        (participant_id, purpose_id),
    ).fetchone()
    if consent is None:
        raise ValueError("该参与者对此用途没有授权记录")
    if consent["status"] == "granted":
        raise ValueError("授权当前有效，无需重新授予")
    next_version = consent["version"] + 1
    updated = conn.execute(
        """UPDATE consents SET version=%s, status='granted',
              granted_at=now(), withdrawn_at=NULL, withdraw_reason=''
            WHERE id=%s RETURNING *""",
        (next_version, consent["id"]),
    ).fetchone()
    conn.execute(
        """INSERT INTO consent_events (consent_id, version, action, actor_identity_id)
           VALUES (%s,%s,'granted',%s)""",
        (consent["id"], next_version, actor_identity_id),
    )
    log_event(conn, actor_identity_id=actor_identity_id, action="consent_granted",
              consent_id=consent["id"],
              detail={"participant_id": participant_id, "purpose_id": purpose_id,
                      "version": next_version})
    return updated


# ---------- CP-1：入队时校验 ----------
def check_request_usable(conn: psycopg.Connection, request_row: dict) -> Optional[str]:
    """返回 None 表示申请当前可用于导出；否则返回拒绝原因。"""
    now = _now()
    if request_row["status"] != "approved":
        return "request_not_approved"
    if request_row["grant_expires_at"] is None or request_row["grant_expires_at"] <= now:
        return "grant_expired"
    participant_ids = list_dataset_participants(conn, request_row["dataset_id"])
    grants = effective_grants(conn, participant_ids, request_row["purpose_id"])
    for pid in participant_ids:
        if not is_grant_effective(grants.get(pid), now):
            return "participant_withdrew"
    return None

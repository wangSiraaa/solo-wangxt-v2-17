"""本地演示用身份机制。

真实系统应有完整登录鉴权；这里为了可复现的本地演示，前端通过
X-Test-Identity 头指定身份（identity_key），所有端点都据此识别参与者/
研究员/管理员。身份与数据均由 seed.sql 预置。
"""
from dataclasses import dataclass
from typing import Optional

import psycopg
from fastapi import Header, HTTPException
from psycopg.types.json import Json


@dataclass
class Actor:
    identity_id: int
    identity_key: str
    role: str
    participant_id: Optional[int] = None
    researcher_id: Optional[int] = None
    admin_id: Optional[int] = None
    label: str = ""


def current_actor(
    x_test_identity: Optional[str] = Header(default=None, alias="X-Test-Identity"),
) -> Actor:
    if not x_test_identity:
        raise HTTPException(status_code=401, detail="缺少 X-Test-Identity 头（本地演示身份）")
    # 在请求级短连接中解析身份
    from .db import get_conn

    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, identity_key, role, participant_id, researcher_id, admin_id, label
               FROM identities WHERE identity_key = %s""",
            (x_test_identity,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail=f"未知演示身份: {x_test_identity}")
    return Actor(
        identity_id=row["id"],
        identity_key=row["identity_key"],
        role=row["role"],
        participant_id=row["participant_id"],
        researcher_id=row["researcher_id"],
        admin_id=row["admin_id"],
        label=row["label"],
    )


def require_role(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise HTTPException(status_code=403, detail=f"该操作仅对 {roles} 开放，当前身份为 {actor.role}")


def log_event(
    conn: psycopg.Connection,
    *,
    actor_identity_id: Optional[int],
    action: str,
    request_id: Optional[int] = None,
    export_id: Optional[int] = None,
    link_id: Optional[int] = None,
    consent_id: Optional[int] = None,
    detail: Optional[dict] = None,
) -> int:
    """追加写入访问事件。该表只追加，应用层没有任何更新/删除路径。"""
    row = conn.execute(
        """INSERT INTO access_events
           (actor_identity_id, action, request_id, export_id, link_id, consent_id, detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (actor_identity_id, action, request_id, export_id, link_id, consent_id,
         Json(detail or {})),
    ).fetchone()
    return row["id"]

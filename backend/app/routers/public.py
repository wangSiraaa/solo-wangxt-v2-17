from fastapi import APIRouter, Depends

from ..auth import Actor, current_actor
from ..db import get_conn

router = APIRouter(tags=["public"])


@router.get("/api/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "service": "consent-withdrawal-demo"}


@router.get("/api/identities")
def list_identities():
    """可切换的测试身份列表（本地演示登录入口）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT identity_key, role, label,
                      participant_id, researcher_id, admin_id
                 FROM identities ORDER BY role, identity_key"""
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/me")
def me(actor: Actor = Depends(current_actor)):
    return {
        "identity_id": actor.identity_id,
        "identity_key": actor.identity_key,
        "role": actor.role,
        "label": actor.label,
        "participant_id": actor.participant_id,
        "researcher_id": actor.researcher_id,
        "admin_id": actor.admin_id,
    }


@router.get("/api/catalog")
def catalog(actor: Actor = Depends(current_actor)):
    """脱敏数据集 + 用途目录，供申请页使用。"""
    with get_conn() as conn:
        datasets = conn.execute(
            """SELECT d.id, d.code, d.title, d.description, d.is_deidentified,
                      (SELECT count(*) FROM dataset_records r WHERE r.dataset_id=d.id) AS record_count,
                      (SELECT count(DISTINCT participant_id) FROM dataset_records r WHERE r.dataset_id=d.id) AS participant_count
                 FROM datasets d ORDER BY d.id"""
        ).fetchall()
        purposes = conn.execute(
            "SELECT id, code, title, description FROM purposes ORDER BY id"
        ).fetchall()
        # 当前各用途的参与者授权计数（供研究员了解数据可得性）
        coverage = conn.execute(
            """SELECT purpose_id,
                      count(*) FILTER (WHERE status='granted') AS granted_count,
                      count(*) FILTER (WHERE status='withdrawn') AS withdrawn_count,
                      count(*) AS total_count
                 FROM consents GROUP BY purpose_id ORDER BY purpose_id"""
        ).fetchall()
    return {
        "datasets": [dict(r) for r in datasets],
        "purposes": [dict(r) for r in purposes],
        "coverage": [dict(r) for r in coverage],
    }


@router.get("/api/datasets/{dataset_id}/sample-records")
def sample_records(dataset_id: int, actor: Actor = Depends(current_actor)):
    """展示本地脱敏样本的前若干行（无需授权即可浏览，用于演示数据形态）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.row_no, p.code AS participant_code, r.payload
                 FROM dataset_records r JOIN participants p ON p.id=r.participant_id
                WHERE r.dataset_id=%s ORDER BY r.row_no LIMIT 20""",
            (dataset_id,),
        ).fetchall()
    return [dict(r) for r in rows]

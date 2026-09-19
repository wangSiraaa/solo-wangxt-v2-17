"""端到端 API 流程：申请 -> 批准 -> 导出 -> 下载 -> 撤回 -> 链接失效。

撤回后历史访问事件必须保留，下载链接再次访问必须被拒绝。
"""

from datetime import timedelta

from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal
from app.main import app
from app.services.exports import run_pending_exports
from app.utils import utcnow

R = {"X-User-Id": "R-101"}
A = {"X-User-Id": "A-001"}
P = {"X-User-Id": "P-001"}


def _events(event_type):
    with SessionLocal() as s:
        return s.query(models.AccessEvent).filter_by(event_type=event_type).all()


def test_full_grant_export_withdraw_link_lifecycle():
    with TestClient(app) as client:
        client.post("/api/demo/reset")

        # 1. 研究员申请数据集访问
        resp = client.post("/api/requests", headers=R, json={
            "dataset_id": "DS-CARDIO-2024",
            "purpose_code": "cardio",
            "project_title": "高血压风险因素分析",
        })
        assert resp.status_code == 201
        request_id = resp.json()["id"]

        # 2. 管理员批准，发放 7 天限时下载权限
        resp = client.post(f"/api/admin/requests/{request_id}/approve",
                           headers=A, json={"days_valid": 7})
        assert resp.status_code == 200
        grant_id = resp.json()["grant_id"]

        # 3. 研究员排队导出并运行 Worker
        resp = client.post("/api/exports", headers=R, json={"grant_id": grant_id})
        assert resp.status_code == 201
        job_id = resp.json()["id"]
        assert run_pending_exports(SessionLocal, delay=0) == [(job_id, "completed")]

        # 4. 取得下载链接并下载（第一次：成功）
        resp = client.get("/api/exports/mine", headers=R)
        export = next(e for e in resp.json()["exports"] if e["id"] == job_id)
        token = export["download_token"]
        assert token and export["downloaded"] is False

        resp = client.get(f"/api/downloads/{token}")
        assert resp.status_code == 200
        assert "participant_id" in resp.text

        resp = client.get("/api/exports/mine", headers=R)
        export = next(e for e in resp.json()["exports"] if e["id"] == job_id)
        assert export["downloaded"] is True  # 前端据此区分"已下载/未下载"

        # 5. 参与者撤回该用途授权
        resp = client.post("/api/participants/me/consents/cardio",
                           headers=P, json={"action": "withdraw"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "withdrawn"

        # 6. 已发放的链接再次访问：重新校验授权 -> 403
        resp = client.get(f"/api/downloads/{token}/check")
        assert resp.json()["valid"] is False
        assert "consent_withdrawn" in resp.json()["reasons"]

        resp = client.get(f"/api/downloads/{token}")
        assert resp.status_code == 403
        assert "consent_withdrawn" in resp.json()["detail"]["reasons"]

        # 7. 撤回后新的导出申请在排队时即被拒绝
        resp = client.post("/api/exports", headers=R, json={"grant_id": grant_id})
        assert resp.status_code == 409
        assert "consent_withdrawn" in resp.json()["detail"]["reasons"]

        # 8. 历史访问记录完整保留：成功与拒绝都有审计
        assert len(_events("download_served")) == 1
        assert len(_events("download_denied")) == 1
        assert len(_events("consent_withdrawn")) == 1
        assert len(_events("export_completed")) == 1


def test_download_link_expiry():
    with TestClient(app) as client:
        client.post("/api/demo/reset")
        resp = client.post("/api/requests", headers=R, json={
            "dataset_id": "DS-CARDIO-2024", "purpose_code": "cardio",
            "project_title": "链接过期测试",
        })
        request_id = resp.json()["id"]
        resp = client.post(f"/api/admin/requests/{request_id}/approve",
                           headers=A, json={"days_valid": 7})
        grant_id = resp.json()["grant_id"]
        resp = client.post("/api/exports", headers=R, json={"grant_id": grant_id})
        job_id = resp.json()["id"]
        run_pending_exports(SessionLocal, delay=0)

        with SessionLocal() as s:
            link = s.query(models.DownloadLink).filter_by(export_job_id=job_id).one()
            link.expires_at = utcnow() - timedelta(hours=1)  # 强制过期
            s.commit()
            token = link.token

        resp = client.get(f"/api/downloads/{token}")
        assert resp.status_code == 403
        assert "link_expired" in resp.json()["detail"]["reasons"]

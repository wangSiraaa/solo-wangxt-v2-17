"""完整业务流程测试：申请 → 限时批准 → 导出入队/执行 → 下载 → 撤回 → 链接失效。"""
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings
from app.db import get_conn
from app.exporter import claim_next_job, process_job
from .conftest import H


def _run_one_job(sleep_fn=lambda _s: None):
    """同步驱动 worker 处理一个任务：claim 事务 + 执行事务。"""
    with get_conn() as conn:
        job = claim_next_job(conn)
        assert job is not None
    with get_conn() as conn:
        result = process_job(conn, job, sleep_fn=sleep_fn)
    return job, result


def _submit_approve_queue(client, purpose_id=1, grant_minutes=60):
    r = client.post("/api/researcher/requests", headers=H["R2001"],
                    json={"dataset_id": 1, "purpose_id": purpose_id,
                          "justification": "测试用途"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = client.post(f"/api/admin/requests/{rid}/decision", headers=H["ADMIN"],
                    json={"approve": True, "grant_minutes": grant_minutes})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/researcher/projects/{rid}/exports", headers=H["R2001"])
    assert r.status_code == 200, r.text
    return rid, r.json()["id"]


def test_identities_and_deidentified_sample(client):
    r = client.get("/api/identities")
    assert r.status_code == 200
    keys = {i["identity_key"] for i in r.json()}
    assert {"participant-1001", "researcher-2001", "admin-3001"} <= keys

    r = client.get("/api/datasets/1/sample-records", headers=H["R2001"])
    rows = r.json()
    assert len(rows) == 8
    # 脱敏样本不含任何直接标识符
    for row in rows:
        assert set(row.keys()) == {"row_no", "participant_code", "payload"}
        assert row["participant_code"].startswith("P-")
        assert "age_band" in row["payload"]  # 年龄段而非精确年龄


def test_full_happy_path_grant_export_download(client):
    rid, job_id = _submit_approve_queue(client)

    # 研究员项目页：任务排队中，尚未下载
    r = client.get(f"/api/researcher/projects/{rid}", headers=H["R2001"])
    project = r.json()
    assert project["grant_active"] is True
    assert project["jobs"][0]["status"] == "queued"
    assert project["jobs"][0]["active_token"] is None

    # worker 执行导出
    job, result = _run_one_job()
    assert result["status"] == "complete"
    assert result["record_count"] == 8
    assert result["token"]

    r = client.get(f"/api/researcher/projects/{rid}", headers=H["R2001"])
    job_view = r.json()["jobs"][0]
    assert job_view["status"] == "complete"
    token = job_view["active_token"]
    assert token

    # CP-4：第一次下载成功（文件内容为脱敏 CSV）
    r = client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])
    assert r.status_code == 200
    body = r.text
    assert "participant_code" in body
    assert "X-Consent-Revalidated-At" in r.headers
    # 已下载状态可被前端识别
    r = client.get(f"/api/researcher/projects/{rid}", headers=H["R2001"])
    assert r.json()["jobs"][0]["links_used"] == 1


def test_cp1_cannot_queue_without_approval(client):
    r = client.post("/api/researcher/requests", headers=H["R2002"],
                    json={"dataset_id": 1, "purpose_id": 1, "justification": "未批先导"})
    rid = r.json()["id"]
    r = client.post(f"/api/researcher/projects/{rid}/exports", headers=H["R2002"])
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "request_not_approved"


def test_cp1_cannot_queue_after_participant_withdraw(client):
    # 批准后先撤回，再尝试入队
    r = client.post("/api/researcher/requests", headers=H["R2002"],
                    json={"dataset_id": 1, "purpose_id": 1, "justification": "撤回拦截"})
    rid = r.json()["id"]
    assert client.post(f"/api/admin/requests/{rid}/decision", headers=H["ADMIN"],
                       json={"approve": True, "grant_minutes": 60}).status_code == 200
    r = client.post("/api/participant/consents/withdraw", headers=H["P1002"],
                    json={"purpose_id": 1, "reason": "不想再参与"})
    assert r.status_code == 200
    assert r.json()["version"] == 2

    r = client.post(f"/api/researcher/projects/{rid}/exports", headers=H["R2002"])
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "participant_withdrew"


def test_cp2_queued_job_cancelled_when_withdrawn_during_processing(client):
    """撤回在 worker“准备期间”完成：执行事务先看到任务已取消/授权已撤回 → cancelled。"""
    rid, job_id = _submit_approve_queue(client)

    # claim 让任务进入 running（模拟 worker 已拾取）
    with get_conn() as conn:
        claimed = claim_next_job(conn)
    assert claimed["status"] == "running"

    # 参与者撤回：running 任务应被连带取消
    r = client.post("/api/participant/consents/withdraw", headers=H["P1001"],
                    json={"purpose_id": 1, "reason": "排队期间撤回"})
    assert r.status_code == 200
    assert job_id in r.json()["cancelled_export_ids"]

    # worker 进入执行事务：状态已是 cancelled，不产出文件
    with get_conn() as conn:
        result = process_job(conn, claimed)
    assert result["produced"] is False
    assert result["status"] == "cancelled"

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM export_jobs WHERE id=%s", (job_id,)).fetchone()
    assert row["status"] == "cancelled"
    assert row["file_path"] is None
    assert row["denial_reason"] == "participant_withdrew"


def test_withdraw_after_export_completes_revokes_link(client):
    """裁决 B 的确定性版本：导出已完成后撤回 → 链接撤销，CP-4 拒绝。

    与真正并发不同的是这里串行发生，但验证“导出越过 CP-2 后撤回”的
    数据状态与下载重新校验逻辑（并发测试中该分支是非确定出现的）。
    """
    rid, job_id = _submit_approve_queue(client, purpose_id=1)
    _, result = _run_one_job()
    assert result["status"] == "complete"
    token = result["token"]

    r = client.post("/api/participant/consents/withdraw", headers=H["P1001"],
                    json={"purpose_id": 1, "reason": "完成后撤回"})
    assert r.status_code == 200
    assert r.json()["revoked_link_ids"]

    r = client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])
    assert r.status_code == 409

    # 重新授予不会让旧链接复活
    r = client.post("/api/participant/consents/regrant", headers=H["P1001"],
                    json={"purpose_id": 1})
    assert r.status_code == 200
    r = client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])
    assert r.status_code == 409


def test_cp2_concurrent_withdraw_vs_export_has_verdict(client):
    """撤回与导出真正并发：两种可能裁决都必须安全。

    worker 已 claim（running）并在“准备阶段”等待；此时参与者发起撤回。
    可接受结果之一：
      A) 撤回先完成 → 任务 cancelled，无文件、无可用链接；
      B) 导出先越过 CP-2 完成 → 有文件，但撤回事务撤销其链接，CP-4 拒绝再下载。
    不可接受：撤回已生效，却仍存在 revoked=FALSE 且可下载的链接。
    """
    import threading

    rid, job_id = _submit_approve_queue(client, purpose_id=1)

    with get_conn() as conn:
        claimed = claim_next_job(conn)
    assert claimed["status"] == "running"

    barrier = threading.Barrier(2)

    def worker_sleep(_seconds):
        # worker 到达检查点前等待撤回线程同时进入
        barrier.wait(timeout=10)

    worker_out = {}

    def worker():
        try:
            with get_conn() as conn:
                worker_out["result"] = process_job(conn, claimed, sleep_fn=worker_sleep)
        except Exception as exc:  # 并发中序列化失败等也算异常，断言处暴露
            worker_out["error"] = repr(exc)

    t = threading.Thread(target=worker)
    t.start()
    barrier.wait(timeout=10)
    # 两者几乎同时：worker 即将取 slot 锁，撤回立即发起
    r = client.post("/api/participant/consents/withdraw", headers=H["P1001"],
                    json={"purpose_id": 1, "reason": "并发撤回"})
    assert r.status_code == 200
    t.join(timeout=15)

    with get_conn() as conn:
        final_job = conn.execute("SELECT * FROM export_jobs WHERE id=%s", (job_id,)).fetchone()
        links = conn.execute("SELECT * FROM download_links WHERE export_id=%s", (job_id,)).fetchall()

    if final_job["status"] == "cancelled":
        # 裁决 A：无文件产出
        assert final_job["file_path"] is None
        assert all(l["revoked"] for l in links)
    else:
        # 裁决 B：导出完成，但链接必须已被撤回撤销
        assert final_job["status"] == "complete"
        assert links and all(l["revoked"] for l in links)
        token = links[0]["token"]
        r2 = client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])
        assert r2.status_code == 409

    # 无论哪种裁决，参与者的授权版本已升级为 withdrawn
    with get_conn() as conn:
        consent = conn.execute(
            "SELECT status, version FROM consents WHERE participant_id=1001 AND purpose_id=1"
        ).fetchone()
    assert consent["status"] == "withdrawn"
    assert consent["version"] == 2


def test_withdraw_revokes_existing_link_and_cp4_revalidates(client):
    """已完成导出、已下载过的链接，在撤回后再次访问必须失效（CP-4 重新校验）。"""
    rid, job_id = _submit_approve_queue(client)
    _, result = _run_one_job()
    token = result["token"]

    # 撤回前可下载
    assert client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"]).status_code == 200

    # 参与者撤回
    r = client.post("/api/participant/consents/withdraw", headers=H["P1001"],
                    json={"purpose_id": 1, "reason": "撤销已发放链接"})
    assert r.status_code == 200

    # 链接被标记撤销
    with get_conn() as conn:
        link = conn.execute("SELECT * FROM download_links WHERE token=%s", (token,)).fetchone()
    assert link["revoked"] is True

    # CP-4：再次访问被拒，且记录 download_denied 事件
    r = client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] in ("link_revoked", "participant_withdrew")

    with get_conn() as conn:
        denied = conn.execute(
            "SELECT count(*) AS n FROM access_events WHERE action='download_denied'"
        ).fetchone()
        revoked_events = conn.execute(
            "SELECT count(*) AS n FROM access_events WHERE action='link_revoked'"
        ).fetchone()
    assert denied["n"] >= 1
    assert revoked_events["n"] >= 1


def test_cp4_expired_grant_window_denied(client):
    rid, job_id = _submit_approve_queue(client, grant_minutes=1)
    _, result = _run_one_job()
    token = result["token"]

    # 直接把窗口推到过去（等价于限时窗口到期）
    with get_conn() as conn:
        conn.execute(
            """UPDATE access_requests SET grant_expires_at = now() - interval '1 minute'
                WHERE id=%s""", (rid,))
        conn.execute(
            "UPDATE download_links SET expires_at = now() - interval '1 minute' WHERE token=%s",
            (token,))

    r = client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] in ("grant_expired", "link_expired")


def test_history_not_deleted_after_withdraw(client):
    """撤回不删除任何历史访问记录。"""
    rid, job_id = _submit_approve_queue(client)
    job, result = _run_one_job()
    token = result["token"]
    client.get(f"/api/researcher/downloads/{token}", headers=H["R2001"])

    before = {}
    with get_conn() as conn:
        for table in ["access_events", "consent_events", "export_jobs", "download_links"]:
            before[table] = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]

    r = client.post("/api/participant/consents/withdraw", headers=H["P1002"],
                    json={"purpose_id": 1, "reason": "历史保留检查"})
    assert r.status_code == 200

    with get_conn() as conn:
        # 只追加：事件数量只增不减
        n_events = conn.execute("SELECT count(*) AS n FROM access_events").fetchone()["n"]
        n_consent_events = conn.execute("SELECT count(*) AS n FROM consent_events").fetchone()["n"]
        completed = conn.execute(
            "SELECT count(*) AS n FROM export_jobs WHERE status='complete'"
        ).fetchone()["n"]
        download_row = conn.execute(
            "SELECT access_count, last_accessed_at FROM download_links WHERE token=%s", (token,)
        ).fetchone()
    assert n_events > before["access_events"]
    assert n_consent_events > before["consent_events"]
    # 已完成任务和已发生的下载事实仍然保留
    assert completed >= 1
    assert download_row["access_count"] >= 1
    assert download_row["last_accessed_at"] is not None


def test_consent_version_history_and_affected_projects(client):
    r = client.get("/api/participant/consents", headers=H["P1001"])
    consents = r.json()
    assert len(consents) == 2
    diabetes = [c for c in consents if c["purpose_id"] == 1][0]
    assert diabetes["status"] == "granted"
    assert diabetes["version"] == 1
    assert diabetes["history"][0]["action"] == "granted"

    # 种子里 P1004 已有 granted→withdrawn 两个版本
    r = client.get("/api/participant/consents", headers={"X-Test-Identity": "participant-1004"})
    cardio = [c for c in r.json() if c["purpose_id"] == 2][0]
    assert cardio["version"] == 2
    assert cardio["status"] == "withdrawn"
    assert [e["action"] for e in cardio["history"]] == ["withdrawn", "granted"]

    # 受影响项目接口（撤回前用 P1003 看心血管用途）
    r = client.get("/api/participant/affected-projects?purpose_id=2",
                   headers={"X-Test-Identity": "participant-1003"})
    assert r.status_code == 200


def test_researcher_cannot_see_others_project(client):
    # R2002 看不到 R2001 的项目（遍历 R2001 的项目 id）
    r = client.get("/api/researcher/projects", headers=H["R2001"])
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    if ids:
        r = client.get(f"/api/researcher/projects/{ids[0]}", headers=H["R2002"])
        assert r.status_code == 403

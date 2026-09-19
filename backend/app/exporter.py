"""导出队列执行（CP-2）与下载链接（CP-4）。

任务状态机：
  queued ──拾取(事务1)──▶ running ──执行事务(先锁授权位)──▶ complete（自动签发下载链接）
                                       └──检查点不通过──▶ cancelled（不生成文件）

锁序约定（防止撤回 × 导出死锁）：
  所有事务都必须“先锁 consent_slots，再锁 export_jobs 行”，顺序一致。
  因此 claim（只锁 job 行）独立成事务并立即提交；执行事务先锁 slots，
  再 SELECT ... FOR UPDATE 锁 job 行，然后检查状态与授权。

“running 阶段”刻意保留一段可观察的处理时间（settings.export_processing_seconds），
位于执行事务加锁之前：此时撤回可以自由完成，随后执行事务看到任务已取消。
若撤回在执行事务取得 slot 锁之后到达，则等待导出完成——文件可能产出，
但撤回事务会撤销其下载链接，且 CP-4 每次访问重新校验，链接不再可用。
两种交错都有确定裁决：不存在“授权已撤回而新产出链接仍可下载”的状态。
"""
import csv
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg

from .config import get_settings
from .consents import (
    effective_grants,
    is_grant_effective,
    list_dataset_participants,
    lock_slots,
)
from .auth import log_event


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_next_job(conn: psycopg.Connection) -> Optional[dict]:
    """原子拾取一个最早的 queued 任务（SKIP LOCKED 防多 worker 重复领取）。

    该更新在调用方的短事务中独立提交：只触碰 export_jobs，不涉及授权锁，
    避免与撤回事务形成相反锁序。
    """
    row = conn.execute(
        """UPDATE export_jobs SET status='running', started_at=now(), updated_at=now()
            WHERE id = (
                SELECT id FROM export_jobs
                 WHERE status='queued'
                 ORDER BY requested_at
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
            )
         RETURNING *"""
    ).fetchone()
    return row


def process_job(conn: psycopg.Connection, job: dict, *, sleep_fn=time.sleep) -> dict:
    """执行 running 任务（调用方事务，按 slots → jobs 的顺序加锁）。"""
    settings = get_settings()

    request_row = conn.execute(
        "SELECT * FROM access_requests WHERE id = %s", (job["request_id"],)
    ).fetchone()
    participant_ids = list_dataset_participants(conn, request_row["dataset_id"])

    # 模拟导出排队后的“数据准备时间”，不持有任何锁。
    # 演示撤回在此期间发生时：撤回事务可直接把任务取消。
    sleep_fn(settings.export_processing_seconds)

    # ===== 统一锁序：先锁授权位 =====
    lock_slots(conn, participant_ids, request_row["purpose_id"])
    # ===== 再锁该任务行，并在锁内重新读取状态（撤回可能已取消它） =====
    fresh_job = conn.execute(
        "SELECT * FROM export_jobs WHERE id=%s FOR UPDATE", (job["id"],)
    ).fetchone()
    if fresh_job["status"] != "running":
        return {"id": job["id"], "status": fresh_job["status"], "produced": False}

    # ===== CP-2：文件写入前的授权检查点（持锁裁决） =====
    denial: Optional[str] = None
    if request_row["grant_expires_at"] is None or request_row["grant_expires_at"] <= _now():
        denial = "grant_expired"
    else:
        grants = effective_grants(conn, participant_ids, request_row["purpose_id"])
        for pid in participant_ids:
            if not is_grant_effective(grants.get(pid)):
                denial = "participant_withdrew"
                break

    if denial:
        conn.execute(
            """UPDATE export_jobs SET status='cancelled', finished_at=now(),
                  denial_reason=%s, updated_at=now() WHERE id=%s""",
            (denial, job["id"]),
        )
        log_event(conn, actor_identity_id=None, action="export_cancelled",
                  export_id=job["id"], request_id=request_row["id"],
                  detail={"checkpoint": "CP-2", "reason": denial,
                          "purpose_id": request_row["purpose_id"]})
        return {"id": job["id"], "status": "cancelled", "produced": False, "reason": denial}

    # ===== 检查点通过：物化导出文件（仅当前仍授权数据主体的记录；
    # 本演示中数据集为整体授予/撤回，保留按参与者过滤的能力） =====
    records = conn.execute(
        """SELECT r.row_no, p.code AS participant_code, r.payload
             FROM dataset_records r
             JOIN participants p ON p.id = r.participant_id
             JOIN consents c ON c.participant_id = p.id AND c.purpose_id = %s
            WHERE r.dataset_id = %s AND c.status = 'granted'
            ORDER BY r.row_no""",
        (request_row["purpose_id"], request_row["dataset_id"]),
    ).fetchall()

    file_path, sha, count = _write_csv(job["id"], records)
    conn.execute(
        """UPDATE export_jobs SET status='complete', finished_at=now(),
              record_count=%s, file_path=%s, file_sha256=%s, updated_at=now()
            WHERE id=%s""",
        (count, file_path, sha, job["id"]),
    )
    log_event(conn, actor_identity_id=None, action="export_completed",
              export_id=job["id"], request_id=request_row["id"],
              detail={"checkpoint": "CP-2", "record_count": count, "file_sha256": sha})

    # 签发下载链接：有效期不超过管理员授予的限时窗口
    token = secrets.token_urlsafe(24)
    conn.execute(
        """INSERT INTO download_links (token, export_id, expires_at)
           VALUES (%s,%s,%s)""",
        (token, job["id"], request_row["grant_expires_at"]),
    )
    return {"id": job["id"], "status": "complete", "produced": True, "token": token,
            "record_count": count}


def _write_csv(job_id: int, records: list[dict]) -> tuple[str, str, int]:
    settings = get_settings()
    os.makedirs(settings.export_dir, exist_ok=True)
    ts = _now().strftime("%Y%m%dT%H%M%S")
    path = os.path.join(settings.export_dir, f"export_{job_id}_{ts}.csv")
    fieldnames = ["row_no", "participant_code"]
    payload_keys: list[str] = []
    for r in records:
        for k in r["payload"]:
            if k not in payload_keys:
                payload_keys.append(k)
    fieldnames.extend(payload_keys)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {"row_no": r["row_no"], "participant_code": r["participant_code"]}
            row.update(r["payload"])
            writer.writerow(row)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return path, h.hexdigest(), len(records)


def run_worker_loop(stop_after: Optional[int] = None) -> None:  # pragma: no cover - 手动运行
    """后台 worker 主循环。每个任务两个事务：claim（提交）→ 执行（提交）。"""
    from .db import get_conn

    processed = 0
    while True:
        job = None
        with get_conn() as conn:
            job = claim_next_job(conn)
            if job is not None:
                log_event(conn, actor_identity_id=None, action="export_started",
                          export_id=job["id"], request_id=job["request_id"],
                          detail={"checkpoint": "worker-claim"})
        if job is None:
            time.sleep(get_settings().worker_poll_seconds)
            continue

        with get_conn() as conn:
            process_job(conn, job)
        processed += 1
        if stop_after is not None and processed >= stop_after:
            return

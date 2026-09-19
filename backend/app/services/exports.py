"""导出队列与 Worker。

撤回与导出并发时的权限检查点（checkpoint）设计：
- 排队时（queue_export）：校验授权，不合法直接拒绝入队；
- 执行前（checkpoint A）：Worker 认领任务后、生成文件前重新校验；
- 提交前（checkpoint B）：文件生成后、标记完成并签发下载链接前，
  在同一事务内做最终校验。撤回若发生在执行窗口内，任务在此被取消，
  半成品文件被删除，不会签发下载链接。

PostgreSQL 下认领与最终校验使用 SELECT ... FOR UPDATE 行锁，
与撤回事务（写 consent_versions + 更新 queued 任务）形成明确的并发边界。
"""

from __future__ import annotations

import csv
import os
import time
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from .. import config, models
from ..utils import utcnow
from .audit import record_event
from .permissions import (
    Decision,
    PermissionDenied,
    current_consent_status,
    evaluate_grant,
)


def queue_export(
    session: Session, *, grant: models.Grant, actor_id: str
) -> models.ExportJob:
    """研究员申请导出。入队即做一次权限校验。"""
    decision = evaluate_grant(session, grant)
    if not decision.allowed:
        raise PermissionDenied(decision)
    job = models.ExportJob(
        grant_id=grant.id,
        researcher_id=grant.researcher_id,
        dataset_id=grant.dataset_id,
        purpose_code=grant.purpose_code,
        status="queued",
    )
    session.add(job)
    session.flush()
    record_event(
        session,
        actor_id=actor_id,
        actor_role="researcher",
        event_type="export_queued",
        grant_id=grant.id,
        export_job_id=job.id,
        purpose_code=grant.purpose_code,
        dataset_id=grant.dataset_id,
    )
    return job


def _locked_job(session: Session, job_id: int) -> models.ExportJob | None:
    query = session.query(models.ExportJob).filter(models.ExportJob.id == job_id)
    if session.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    return query.first()


def _cancel_job(session: Session, job: models.ExportJob, decision: Decision) -> None:
    job.status = "cancelled"
    job.cancel_reason = ",".join(decision.reasons)
    job.finished_at = utcnow()
    record_event(
        session,
        actor_id="system",
        actor_role="system",
        event_type="export_cancelled",
        export_job_id=job.id,
        grant_id=job.grant_id,
        purpose_code=job.purpose_code,
        dataset_id=job.dataset_id,
        detail={
            "reasons": decision.reasons,
            "withdrawn_participants": decision.withdrawn_participants,
        },
    )


def _generate_csv(session: Session, job: models.ExportJob) -> tuple[str, int]:
    """生成导出文件。纵深防御：只写入当前仍处于 granted 状态的参与者的行。"""
    os.makedirs(config.EXPORT_DIR, exist_ok=True)
    records = (
        session.query(models.DatasetRecord).filter_by(dataset_id=job.dataset_id).all()
    )
    rows = [
        r
        for r in records
        if current_consent_status(session, r.participant_id, job.purpose_code)
        == "granted"
    ]
    keys = sorted({k for r in rows for k in (r.payload or {})})
    path = os.path.join(config.EXPORT_DIR, f"export-{job.id}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["participant_id", *keys])
        for record in rows:
            writer.writerow(
                [record.participant_id, *[(record.payload or {}).get(k, "") for k in keys]]
            )
    return path, len(rows)


def process_one(
    session_factory: sessionmaker, job_id: int, delay: float | None = None
) -> str:
    """处理单个导出任务，返回最终状态。"""
    delay = config.EXPORT_WORKER_DELAY_SECONDS if delay is None else delay

    # 1) 认领任务（PostgreSQL 下行锁，与撤回事务互斥）
    with session_factory() as session:
        job = _locked_job(session, job_id)
        if job is None:
            return "missing"
        if job.status != "queued":
            return job.status
        job.status = "running"
        job.started_at = utcnow()
        record_event(
            session,
            actor_id="system",
            actor_role="system",
            event_type="export_started",
            export_job_id=job.id,
            grant_id=job.grant_id,
            purpose_code=job.purpose_code,
            dataset_id=job.dataset_id,
        )
        session.commit()

    # 2) 权限检查点 A：执行前重新校验
    with session_factory() as session:
        job = session.get(models.ExportJob, job_id)
        decision = evaluate_grant(session, job.grant)
        if not decision.allowed:
            _cancel_job(session, job, decision)
            session.commit()
            return "cancelled"

    # 3) 导出执行窗口（演示用延迟，让"撤回 vs 导出"的并发可观察）
    if delay:
        time.sleep(delay)

    # 4) 生成文件（只包含当前已授权参与者的行）
    with session_factory() as session:
        job = session.get(models.ExportJob, job_id)
        path, row_count = _generate_csv(session, job)

    # 5) 权限检查点 B：提交前最终校验，与签发下载链接在同一事务
    with session_factory() as session:
        job = _locked_job(session, job_id)
        decision = evaluate_grant(session, job.grant)
        if not decision.allowed:
            _cancel_job(session, job, decision)
            session.commit()
            if os.path.exists(path):
                os.remove(path)
            return "cancelled"

        job.status = "completed"
        job.file_path = path
        job.row_count = row_count
        job.finished_at = utcnow()
        token = uuid.uuid4().hex
        session.add(
            models.DownloadLink(
                token=token,
                export_job_id=job.id,
                expires_at=utcnow() + timedelta(hours=config.DOWNLOAD_LINK_TTL_HOURS),
            )
        )
        record_event(
            session,
            actor_id="system",
            actor_role="system",
            event_type="export_completed",
            export_job_id=job.id,
            grant_id=job.grant_id,
            purpose_code=job.purpose_code,
            dataset_id=job.dataset_id,
            detail={"row_count": row_count},
        )
        record_event(
            session,
            actor_id="system",
            actor_role="system",
            event_type="download_issued",
            export_job_id=job.id,
            grant_id=job.grant_id,
            purpose_code=job.purpose_code,
            dataset_id=job.dataset_id,
            detail={"token": token, "ttl_hours": config.DOWNLOAD_LINK_TTL_HOURS},
        )
        session.commit()
        return "completed"


def run_pending_exports(
    session_factory: sessionmaker, delay: float | None = None
) -> list[tuple[int, str]]:
    with session_factory() as session:
        ids = [
            row[0]
            for row in session.query(models.ExportJob.id)
            .filter_by(status="queued")
            .order_by(models.ExportJob.id)
            .all()
        ]
    return [(job_id, process_one(session_factory, job_id, delay=delay)) for job_id in ids]


def worker_loop(session_factory: sessionmaker, stop_event) -> None:
    """后台轮询 Worker。演示环境用；生产可替换为 Celery/RQ 等。"""
    while not stop_event.is_set():
        try:
            run_pending_exports(session_factory)
        except Exception as exc:  # noqa: BLE001 - worker 不得因单批失败退出
            print(f"[export-worker] batch failed: {exc}")
        stop_event.wait(config.EXPORT_WORKER_INTERVAL_SECONDS)

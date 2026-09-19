from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base
from .utils import utcnow


class Participant(Base):
    """研究参与者（样本数据均为脱敏虚构身份）。"""

    __tablename__ = "participants"
    id = Column(String, primary_key=True)  # e.g. "P-001"
    label = Column(String, nullable=False)  # 匿名化标签，如 "受试者-001"


class Researcher(Base):
    __tablename__ = "researchers"
    id = Column(String, primary_key=True)  # e.g. "R-101"
    name = Column(String, nullable=False)
    affiliation = Column(String, nullable=False)


class Admin(Base):
    __tablename__ = "admins"
    id = Column(String, primary_key=True)  # e.g. "A-001"
    name = Column(String, nullable=False)


class Purpose(Base):
    """数据用途类别。授权与撤回都按用途进行。"""

    __tablename__ = "purposes"
    code = Column(String, primary_key=True)  # e.g. "cardio"
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(String, primary_key=True)  # e.g. "DS-CARDIO-2024"
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")


class DatasetRecord(Base):
    """脱敏后的研究记录，每行归属一位参与者。"""

    __tablename__ = "dataset_records"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), index=True, nullable=False)
    participant_id = Column(
        String, ForeignKey("participants.id"), index=True, nullable=False
    )
    payload = Column(JSON, nullable=False, default=dict)


class ConsentVersion(Base):
    """授权版本链：每次授权/撤回追加一个新版本，历史版本永不修改。"""

    __tablename__ = "consent_versions"
    __table_args__ = (
        UniqueConstraint("participant_id", "purpose_code", "version"),
    )
    id = Column(Integer, primary_key=True)
    participant_id = Column(
        String, ForeignKey("participants.id"), index=True, nullable=False
    )
    purpose_code = Column(
        String, ForeignKey("purposes.code"), index=True, nullable=False
    )
    version = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # granted | withdrawn
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AccessRequest(Base):
    """研究员的数据集访问申请。"""

    __tablename__ = "access_requests"
    id = Column(Integer, primary_key=True)
    researcher_id = Column(
        String, ForeignKey("researchers.id"), index=True, nullable=False
    )
    project_title = Column(String, nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    purpose_code = Column(String, ForeignKey("purposes.code"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending|approved|denied
    created_at = Column(DateTime, nullable=False, default=utcnow)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String, nullable=True)
    decision_note = Column(String, nullable=True)

    grant = relationship("Grant", back_populates="request", uselist=False)


class Grant(Base):
    """数据管理员按用途发放的限时下载权限。"""

    __tablename__ = "grants"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("access_requests.id"), nullable=False)
    researcher_id = Column(
        String, ForeignKey("researchers.id"), index=True, nullable=False
    )
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    purpose_code = Column(String, ForeignKey("purposes.code"), nullable=False)
    granted_by = Column(String, ForeignKey("admins.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)

    request = relationship("AccessRequest", back_populates="grant")


class ExportJob(Base):
    """导出任务：queued -> running -> completed | cancelled | failed。"""

    __tablename__ = "export_jobs"
    id = Column(Integer, primary_key=True)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=False)
    researcher_id = Column(
        String, ForeignKey("researchers.id"), index=True, nullable=False
    )
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    purpose_code = Column(String, ForeignKey("purposes.code"), nullable=False)
    status = Column(String, nullable=False, default="queued")
    cancel_reason = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    row_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    grant = relationship("Grant")
    download_links = relationship("DownloadLink", back_populates="export_job")


class DownloadLink(Base):
    """已发放的下载链接。每次访问都重新校验授权，不做一次性失效删除。"""

    __tablename__ = "download_links"
    token = Column(String, primary_key=True)
    export_job_id = Column(
        Integer, ForeignKey("export_jobs.id"), index=True, nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)

    export_job = relationship("ExportJob", back_populates="download_links")


class AccessEvent(Base):
    """不可变审计日志。撤回授权不会删除历史访问记录。"""

    __tablename__ = "access_events"
    id = Column(Integer, primary_key=True)
    actor_id = Column(String, nullable=False)
    actor_role = Column(String, nullable=False)  # researcher|admin|participant|system
    event_type = Column(String, index=True, nullable=False)
    request_id = Column(Integer, nullable=True)
    grant_id = Column(Integer, nullable=True)
    export_job_id = Column(Integer, nullable=True)
    participant_id = Column(String, nullable=True)
    purpose_code = Column(String, nullable=True)
    dataset_id = Column(String, nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

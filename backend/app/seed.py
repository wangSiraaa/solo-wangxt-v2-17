"""本地脱敏样本数据与测试身份。

所有参与者、测量值均为虚构：无真实姓名/证件号/联系方式，
生理指标为合成随机值，仅用于演示授权-导出-撤回流程。
"""

from __future__ import annotations

import random

from sqlalchemy.orm import Session

from . import models

PURPOSES = [
    ("cardio", "心血管研究", "心血管疾病风险因素与预后分析"),
    ("diabetes", "糖尿病研究", "糖代谢异常与并发症队列研究"),
    ("genomics", "基因组分析", "遗传变异与表型关联分析"),
]

DATASETS = [
    ("DS-CARDIO-2024", "心血管队列 2024", "1,200 例年度随访的脱敏心血管指标子集"),
    ("DS-METAB-2024", "代谢组学队列 2024", "代谢组学与体成分测量脱敏子集"),
]

# 每个数据集包含哪些参与者
DATASET_MEMBERS = {
    "DS-CARDIO-2024": ["P-001", "P-002", "P-003", "P-004", "P-005", "P-006"],
    "DS-METAB-2024": ["P-004", "P-005", "P-006", "P-007", "P-008", "P-009", "P-010"],
}

RESEARCHERS = [
    ("R-101", "陈研（博士）", "国立心血管病中心"),
    ("R-102", "帕特尔（博士）", "内分泌与代谢研究所"),
]

ADMINS = [("A-001", "王数据（管理员）")]


def _synthetic_cardio_record(rng: random.Random) -> dict:
    return {
        "age_band": rng.choice(["30-39", "40-49", "50-59", "60-69"]),
        "sex": rng.choice(["F", "M"]),
        "resting_hr": rng.randint(55, 95),
        "systolic_bp": rng.randint(100, 165),
        "diastolic_bp": rng.randint(60, 100),
        "ldl_mmol_l": round(rng.uniform(1.8, 4.9), 1),
    }


def _synthetic_metab_record(rng: random.Random) -> dict:
    return {
        "age_band": rng.choice(["30-39", "40-49", "50-59", "60-69"]),
        "sex": rng.choice(["F", "M"]),
        "bmi": round(rng.uniform(18.5, 33.0), 1),
        "fasting_glucose": round(rng.uniform(4.2, 8.5), 1),
        "hba1c_pct": round(rng.uniform(4.8, 7.4), 1),
    }


def seed(session: Session) -> bool:
    """空库时写入样本数据。返回是否执行了写入。"""
    if session.query(models.Purpose).count() > 0:
        return False

    rng = random.Random(20240917)

    for code, name, desc in PURPOSES:
        session.add(models.Purpose(code=code, name=name, description=desc))
    for ds_id, name, desc in DATASETS:
        session.add(models.Dataset(id=ds_id, name=name, description=desc))
    for rid, name, affiliation in RESEARCHERS:
        session.add(models.Researcher(id=rid, name=name, affiliation=affiliation))
    for aid, name in ADMINS:
        session.add(models.Admin(id=aid, name=name))

    participants = [f"P-{i:03d}" for i in range(1, 11)]
    for pid in participants:
        session.add(models.Participant(id=pid, label=f"受试者-{pid[-3:]}"))

    for ds_id, members in DATASET_MEMBERS.items():
        for pid in members:
            payload = (
                _synthetic_cardio_record(rng)
                if ds_id == "DS-CARDIO-2024"
                else _synthetic_metab_record(rng)
            )
            session.add(
                models.DatasetRecord(dataset_id=ds_id, participant_id=pid, payload=payload)
            )

    # 初始授权：全员授予 cardio 与 diabetes；P-001..P-005 额外授予 genomics
    for pid in participants:
        for purpose in ("cardio", "diabetes"):
            session.add(
                models.ConsentVersion(
                    participant_id=pid, purpose_code=purpose, version=1, status="granted"
                )
            )
    for pid in participants[:5]:
        session.add(
            models.ConsentVersion(
                participant_id=pid, purpose_code="genomics", version=1, status="granted"
            )
        )
    return True


if __name__ == "__main__":
    from .db import Base, SessionLocal, engine

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        created = seed(session)
        session.commit()
    print("seeded" if created else "already seeded")

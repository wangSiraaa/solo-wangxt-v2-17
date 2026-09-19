from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..db import get_session
from ..deps import Identity, get_identity

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/datasets")
def list_datasets(
    session: Session = Depends(get_session),
    identity: Identity = Depends(get_identity),
):
    datasets = []
    for ds in session.query(models.Dataset).order_by(models.Dataset.id).all():
        datasets.append(
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "record_count": session.query(models.DatasetRecord)
                .filter_by(dataset_id=ds.id)
                .count(),
                "participant_count": session.query(
                    models.DatasetRecord.participant_id
                )
                .filter_by(dataset_id=ds.id)
                .distinct()
                .count(),
            }
        )
    purposes = [
        {"code": p.code, "name": p.name, "description": p.description}
        for p in session.query(models.Purpose).order_by(models.Purpose.code).all()
    ]
    return {"datasets": datasets, "purposes": purposes, "me": identity.user_id}

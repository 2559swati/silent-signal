from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.assets import Asset
from app.schemas.assets import PaginatedAssets, AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=PaginatedAssets)
def list_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(healthy|watch|emerging|critical)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Asset)
    if status:
        query = query.filter(Asset.status == status)

    total = query.count()
    items = (
        query.order_by(Asset.external_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedAssets(total=total, page=page, page_size=page_size, items=items)

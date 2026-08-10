from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Packet
from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["packets"])


class ImportedRequest(BaseModel):
    imported_by: Optional[str] = None
    ptu_ref: Optional[str] = None
    comment: Optional[str] = None


class PacketSummary(BaseModel):
    packet_id: UUID
    status: str
    document_type: Optional[str] = None
    org_id: str
    warehouse_id: str
    telegram_user_id: str
    photos_count: int
    document_number: Optional[str] = None
    document_date: Optional[str] = None
    supplier_name: Optional[str] = None
    overall_confidence: Optional[float] = None
    error_message: Optional[str] = None
    storage_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    recognized_at: Optional[datetime] = None
    imported_at: Optional[datetime] = None
    imported_by: Optional[str] = None
    ptu_ref: Optional[str] = None


class PacketListResponse(BaseModel):
    items: list[PacketSummary]
    total: int
    limit: int
    offset: int


def _summary(p: Packet) -> PacketSummary:
    return PacketSummary(
        packet_id=p.id,
        status=p.status,
        document_type=p.document_type,
        org_id=p.org_id,
        warehouse_id=p.warehouse_id,
        telegram_user_id=str(p.telegram_user_id),
        photos_count=p.photos_count,
        document_number=p.document_number,
        document_date=p.document_date.isoformat() if p.document_date else None,
        supplier_name=p.supplier_name,
        overall_confidence=float(p.overall_confidence) if p.overall_confidence is not None else None,
        error_message=p.error_message,
        storage_path=p.storage_path,
        created_at=p.created_at,
        updated_at=p.updated_at,
        recognized_at=p.recognized_at,
        imported_at=p.imported_at,
        imported_by=p.imported_by,
        ptu_ref=p.ptu_ref,
    )


async def require_bearer(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Bearer required"})
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.api_bearer_token:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Invalid token"})


@router.get("/packets", response_model=PacketListResponse, dependencies=[Depends(require_bearer)])
async def list_packets(
    status: Optional[str] = Query(default="ready"),
    org_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> PacketListResponse:
    filters = []
    if status:
        filters.append(Packet.status == status)
    if org_id:
        filters.append(Packet.org_id == org_id)
    if warehouse_id:
        filters.append(Packet.warehouse_id == warehouse_id)

    total = await session.scalar(select(func.count()).select_from(Packet).where(*filters)) or 0
    rows = (
        await session.scalars(
            select(Packet)
            .where(*filters)
            .order_by(Packet.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PacketListResponse(items=[_summary(p) for p in rows], total=total, limit=limit, offset=offset)


@router.get("/packets/{packet_id}", response_model=PacketSummary, dependencies=[Depends(require_bearer)])
async def get_packet(packet_id: UUID, session: AsyncSession = Depends(get_session)) -> PacketSummary:
    packet = await session.get(Packet, packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Packet not found"})
    return _summary(packet)


@router.get("/packets/{packet_id}/result", dependencies=[Depends(require_bearer)])
async def get_packet_result(packet_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    packet = await session.get(Packet, packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Packet not found"})
    if packet.status not in ("ready", "imported"):
        raise HTTPException(
            status_code=409,
            detail={"code": "PACKET_NOT_READY", "message": f"Status is {packet.status}"},
        )
    if not packet.result_json:
        raise HTTPException(status_code=409, detail={"code": "NO_RESULT", "message": "result.json missing"})
    return packet.result_json


@router.post("/packets/{packet_id}/imported", response_model=PacketSummary, dependencies=[Depends(require_bearer)])
async def mark_imported(
    packet_id: UUID,
    body: ImportedRequest = ImportedRequest(),
    session: AsyncSession = Depends(get_session),
) -> PacketSummary:
    packet = await session.get(Packet, packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Packet not found"})
    if packet.status == "imported":
        return _summary(packet)
    if packet.status != "ready":
        raise HTTPException(
            status_code=409,
            detail={"code": "INVALID_STATUS", "message": f"Cannot import from status {packet.status}"},
        )
    packet.status = "imported"
    packet.imported_at = datetime.now(timezone.utc)
    packet.imported_by = body.imported_by
    packet.ptu_ref = body.ptu_ref
    await session.commit()
    await session.refresh(packet)
    return _summary(packet)

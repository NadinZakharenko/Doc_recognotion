from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


packet_status_enum = ENUM(
    "draft",
    "queued",
    "processing",
    "ready",
    "error",
    "imported",
    name="packet_status",
    create_type=False,
)

document_type_enum = ENUM(
    "torg12",
    "upd",
    "unknown",
    name="document_type",
    create_type=False,
)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org_id: Mapped[str] = mapped_column(Text, ForeignKey("orgs.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    is_whitelisted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserBinding(Base):
    __tablename__ = "user_bindings"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_user_id"), primary_key=True
    )
    org_id: Mapped[str] = mapped_column(Text, ForeignKey("orgs.id"), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(Text, ForeignKey("warehouses.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Packet(Base):
    __tablename__ = "packets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    status: Mapped[str] = mapped_column(packet_status_enum, nullable=False, default="draft")
    document_type: Mapped[Optional[str]] = mapped_column(document_type_enum)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_user_id"), nullable=False)
    org_id: Mapped[str] = mapped_column(Text, ForeignKey("orgs.id"), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(Text, ForeignKey("warehouses.id"), nullable=False)
    storage_path: Mapped[Optional[str]] = mapped_column(Text)
    photos_count: Mapped[int] = mapped_column(Integer, default=0)
    document_number: Mapped[Optional[str]] = mapped_column(Text)
    document_date: Mapped[Optional[date]] = mapped_column(Date)
    supplier_name: Mapped[Optional[str]] = mapped_column(Text)
    overall_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    result_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    recognized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    imported_by: Mapped[Optional[str]] = mapped_column(Text)
    ptu_ref: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    files: Mapped[list["PacketFile"]] = relationship(back_populates="packet")


class PacketFile(Base):
    __tablename__ = "packet_files"
    __table_args__ = (UniqueConstraint("packet_id", "seq_no"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    packet_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("packets.id", ondelete="CASCADE"))
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, default="image/jpeg")
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(Text)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(Text)
    file_unique_id: Mapped[Optional[str]] = mapped_column(Text)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    packet: Mapped["Packet"] = relationship(back_populates="files")


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerJob(Base):
    __tablename__ = "worker_jobs"
    __table_args__ = (UniqueConstraint("packet_id", "job_type"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    packet_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("packets.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(Text, default="recognize")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[Optional[str]] = mapped_column(Text)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""OCR worker: claim jobs with SKIP LOCKED, recognize via anydoc (+ Firecrawl OCR)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Packet, PacketFile
from app.db.session import SessionLocal
from app.ocr.pipeline import recognize_packet_files
from app.storage import get_storage

logger = logging.getLogger(__name__)


async def claim_job(session: AsyncSession, worker_id: str) -> dict | None:
    row = (
        await session.execute(
            text(
                """
                UPDATE worker_jobs
                SET locked_at = now(), locked_by = :worker_id, attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM worker_jobs
                    WHERE locked_at IS NULL AND run_after <= now()
                    ORDER BY run_after
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, packet_id, job_type, attempts
                """
            ),
            {"worker_id": worker_id},
        )
    ).mappings().first()
    await session.commit()
    return dict(row) if row else None


async def _load_files(session: AsyncSession, packet: Packet) -> list[dict]:
    storage = get_storage()
    q = await session.scalars(
        select(PacketFile).where(PacketFile.packet_id == packet.id).order_by(PacketFile.seq_no)
    )
    files = []
    for pf in q.all():
        data = await storage.get_bytes(pf.storage_key)
        files.append(
            {
                "filename": pf.filename,
                "content_type": pf.content_type,
                "data": data,
                "file_id": str(pf.id),
            }
        )
    return files


async def process_recognize(session: AsyncSession, packet_id, attempts: int) -> None:
    settings = get_settings()
    packet = await session.get(Packet, packet_id)
    if not packet:
        return

    packet.status = "processing"
    await session.commit()

    files = await _load_files(session, packet)
    source_images = [
        {
            "file_id": f["file_id"],
            "filename": f["filename"],
            "content_type": f.get("content_type") or "application/octet-stream",
            "sha256": None,
            "page_hint": i + 1,
        }
        for i, f in enumerate(files)
    ]

    if settings.ocr_mode == "stub":
        fields = {
            "document_type": "unknown",
            "header": {"number": None, "date": None},
            "lines": [],
            "totals": {},
            "warnings": [{"code": "OTHER", "message": "Stub OCR", "line_no": None}],
            "overall_confidence": 0.0,
            "ocr_provider": "stub",
            "markdown": "",
        }
    else:
        fields = await recognize_packet_files(settings, files)

    recognized_at = datetime.now(timezone.utc)
    result = {
        "schema_version": "1.0",
        "packet_id": str(packet.id),
        "document_type": fields.get("document_type") or "unknown",
        "header": fields.get("header") or {"number": None, "date": None},
        "lines": fields.get("lines") or [],
        "totals": fields.get("totals") or {},
        "meta": {
            "org_id": packet.org_id,
            "warehouse_id": packet.warehouse_id,
            "telegram_user_id": str(packet.telegram_user_id),
            "created_at": packet.created_at.isoformat() if packet.created_at else None,
            "recognized_at": recognized_at.isoformat(),
            "overall_confidence": float(fields.get("overall_confidence") or 0),
            "ocr_provider": fields.get("ocr_provider") or settings.ocr_mode,
            "source_images": source_images,
        },
        "warnings": fields.get("warnings") or [],
    }
    markdown = fields.get("markdown") or ""

    storage = get_storage()
    if packet.storage_path:
        result_path = f"{packet.storage_path.rstrip('/')}/result.json"
        await storage.put_bytes(
            result_path,
            json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )
        if markdown:
            await storage.put_bytes(
                f"{packet.storage_path.rstrip('/')}/recognized.md",
                markdown.encode("utf-8"),
                "text/markdown",
            )

    packet.result_json = result
    packet.status = "ready"
    packet.recognized_at = recognized_at
    packet.document_type = result["document_type"]
    packet.overall_confidence = result["meta"]["overall_confidence"]
    packet.document_number = (result.get("header") or {}).get("number")
    date_s = (result.get("header") or {}).get("date")
    if date_s:
        try:
            packet.document_date = datetime.strptime(date_s, "%Y-%m-%d").date()
        except ValueError:
            pass
    supplier = ((result.get("header") or {}).get("supplier") or {})
    if isinstance(supplier, dict):
        packet.supplier_name = supplier.get("name")

    has_signal = bool(result.get("lines")) or bool((result.get("header") or {}).get("number"))
    if settings.ocr_mode not in ("stub",) and not has_signal and not markdown:
        packet.status = "error"
        packet.error_message = "; ".join(
            w.get("message", "") for w in (result.get("warnings") or []) if w.get("message")
        )[:2000] or "Recognition produced empty output"

    await session.commit()

    await session.execute(
        text("DELETE FROM worker_jobs WHERE packet_id = :pid AND job_type = 'recognize'"),
        {"pid": packet_id},
    )
    await session.commit()
    logger.info(
        "Packet %s → %s via %s (attempt %s)",
        packet_id,
        packet.status,
        result["meta"]["ocr_provider"],
        attempts,
    )


async def fail_job(session: AsyncSession, job_id, packet_id, error: str) -> None:
    await session.execute(
        text(
            """
            UPDATE worker_jobs
            SET locked_at = NULL, locked_by = NULL, last_error = :err,
                run_after = now() + interval '30 seconds'
            WHERE id = :id
            """
        ),
        {"id": job_id, "err": error[:2000]},
    )
    packet = await session.get(Packet, packet_id)
    if packet and packet.status == "processing":
        packet.status = "error"
        packet.error_message = error[:2000]
    await session.commit()


async def run_forever() -> None:
    settings = get_settings()
    worker_id = settings.worker_id or f"worker-{uuid4().hex[:8]}"
    logger.info(
        "Worker %s started, poll=%ss, ocr_mode=%s, yandex=%s, grok=%s, openai=%s",
        worker_id,
        settings.worker_poll_seconds,
        settings.ocr_mode,
        "yes" if settings.yandex_cloud_api_key else "no",
        "yes" if settings.xai_api_key else "no",
        "yes" if (settings.openai_api_key or settings.ocr_api_key) else "no",
    )

    while True:
        try:
            async with SessionLocal() as session:
                job = await claim_job(session, worker_id)
                if not job:
                    await asyncio.sleep(settings.worker_poll_seconds)
                    continue
                try:
                    await process_recognize(session, job["packet_id"], job["attempts"])
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Job %s failed", job["id"])
                    await fail_job(session, job["id"], job["packet_id"], str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            await asyncio.sleep(settings.worker_poll_seconds)


def main() -> None:
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()

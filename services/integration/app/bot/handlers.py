from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.api import TelegramClient
from app.config import get_settings
from app.db.models import Org, Packet, PacketFile, User, UserBinding, Warehouse, WorkerJob
from app.storage import build_packet_path, get_storage

logger = logging.getLogger(__name__)


def main_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✅ Завершить пакет", "callback_data": "finish"}],
            [
                {"text": "📋 Мой контекст", "callback_data": "context"},
                {"text": "🏷 Сменить склад", "callback_data": "pick_wh"},
            ],
            [{"text": "🏢 Сменить организацию", "callback_data": "pick_org"}],
        ]
    }


async def ensure_user(session: AsyncSession, user_id: int, display_name: str | None) -> User:
    user = await session.get(User, user_id)
    if user:
        if display_name and user.display_name != display_name:
            user.display_name = display_name
        user.is_whitelisted = True
        await session.commit()
        return user

    user = User(telegram_user_id=user_id, display_name=display_name, is_whitelisted=True)
    session.add(user)
    await session.commit()
    return user


async def get_binding(session: AsyncSession, user_id: int) -> UserBinding | None:
    return await session.get(UserBinding, user_id)


async def set_binding(session: AsyncSession, user_id: int, org_id: str, warehouse_id: str) -> UserBinding:
    wh = await session.get(Warehouse, warehouse_id)
    if not wh or wh.org_id != org_id:
        raise ValueError("warehouse does not belong to org")

    stmt = insert(UserBinding).values(
        telegram_user_id=user_id,
        org_id=org_id,
        warehouse_id=warehouse_id,
    ).on_conflict_do_update(
        index_elements=[UserBinding.telegram_user_id],
        set_={"org_id": org_id, "warehouse_id": warehouse_id, "updated_at": datetime.now(timezone.utc)},
    )
    await session.execute(stmt)
    await session.commit()
    binding = await session.get(UserBinding, user_id)
    assert binding is not None
    return binding


async def ensure_default_binding(session: AsyncSession, user_id: int) -> UserBinding | None:
    binding = await get_binding(session, user_id)
    if binding:
        return binding
    orgs = (await session.scalars(select(Org).where(Org.is_active.is_(True)).order_by(Org.id))).all()
    if len(orgs) != 1:
        return None
    whs = (
        await session.scalars(
            select(Warehouse).where(Warehouse.org_id == orgs[0].id, Warehouse.is_active.is_(True)).order_by(Warehouse.id)
        )
    ).all()
    if len(whs) != 1:
        return None
    return await set_binding(session, user_id, orgs[0].id, whs[0].id)


async def context_text(session: AsyncSession, user_id: int) -> str:
    binding = await get_binding(session, user_id)
    if not binding:
        return "Контекст не задан. Выберите организацию и склад."
    org = await session.get(Org, binding.org_id)
    wh = await session.get(Warehouse, binding.warehouse_id)
    draft = (
        await session.scalars(
            select(Packet).where(Packet.telegram_user_id == user_id, Packet.status == "draft")
        )
    ).first()
    photos = draft.photos_count if draft else 0
    return (
        f"Организация: {org.name if org else binding.org_id}\n"
        f"Склад: {wh.name if wh else binding.warehouse_id}\n"
        f"Фото в текущем пакете: {photos}\n\n"
        "Пришлите фото ТОРГ-12/УПД, затем нажмите «Завершить пакет»."
    )


async def orgs_keyboard(session: AsyncSession) -> dict[str, Any]:
    orgs = (await session.scalars(select(Org).where(Org.is_active.is_(True)).order_by(Org.name))).all()
    rows = [[{"text": o.name, "callback_data": f"org:{o.id}"}] for o in orgs]
    return {"inline_keyboard": rows or [[{"text": "Нет организаций", "callback_data": "noop"}]]}


async def warehouses_keyboard(session: AsyncSession, org_id: str) -> dict[str, Any]:
    whs = (
        await session.scalars(
            select(Warehouse).where(Warehouse.org_id == org_id, Warehouse.is_active.is_(True)).order_by(Warehouse.name)
        )
    ).all()
    rows = [[{"text": w.name, "callback_data": f"wh:{w.id}"}] for w in whs]
    return {"inline_keyboard": rows or [[{"text": "Нет складов", "callback_data": "noop"}]]}


async def get_or_create_draft(session: AsyncSession, user_id: int, binding: UserBinding) -> Packet:
    draft = (
        await session.scalars(
            select(Packet).where(Packet.telegram_user_id == user_id, Packet.status == "draft")
        )
    ).first()
    if draft:
        return draft

    packet_id = uuid4()
    settings = get_settings()
    user = await session.get(User, user_id)
    user_label = (user.display_name if user and user.display_name else str(user_id)).replace("/", "_")
    storage_path = build_packet_path(
        disk_root=settings.yandex_disk_root if settings.storage_backend == "yandex" else "",
        org_id=binding.org_id,
        warehouse_id=binding.warehouse_id,
        user_label=user_label,
        date_str=date.today().isoformat(),
        packet_id=str(packet_id),
    )
    # local backend: path relative to LOCAL_STORAGE_ROOT without leading slash root name
    if settings.storage_backend == "local":
        storage_path = build_packet_path(
            disk_root="packets",
            org_id=binding.org_id,
            warehouse_id=binding.warehouse_id,
            user_label=user_label,
            date_str=date.today().isoformat(),
            packet_id=str(packet_id),
        )

    draft = Packet(
        id=packet_id,
        status="draft",
        telegram_user_id=user_id,
        org_id=binding.org_id,
        warehouse_id=binding.warehouse_id,
        storage_path=storage_path,
        photos_count=0,
    )
    session.add(draft)
    await session.commit()
    await session.refresh(draft)
    return draft


async def add_photo_to_draft(
    session: AsyncSession,
    tg: TelegramClient,
    user_id: int,
    chat_id: int,
    file_id: str,
    file_unique_id: str | None,
) -> None:
    binding = await get_binding(session, user_id)
    if not binding:
        await tg.send_message(chat_id, "Сначала выберите организацию и склад.", reply_markup=await orgs_keyboard(session))
        return

    packet = await get_or_create_draft(session, user_id, binding)
    existing = (
        await session.scalars(select(PacketFile).where(PacketFile.packet_id == packet.id))
    ).all()
    seq = max((f.seq_no for f in existing), default=0) + 1
    filename = f"{seq:03d}.jpg"

    # Ack immediately — download/storage can take seconds or fail on VPN
    await tg.send_message(
        chat_id,
        f"Получил фото, сохраняю как №{seq}…",
        reply_markup=main_keyboard(),
    )

    try:
        meta = await tg.get_file(file_id)
        file_path = meta.get("file_path")
        if not file_path:
            await tg.send_message(chat_id, "Не удалось получить файл из Telegram.")
            return
        data = await tg.download_file(file_path)

        storage = get_storage()
        assert packet.storage_path
        images_dir = f"{packet.storage_path.rstrip('/')}/images"
        await storage.ensure_dir(images_dir)
        storage_key = f"{images_dir}/{filename}"
        await storage.put_bytes(storage_key, data, "image/jpeg")

        session.add(
            PacketFile(
                packet_id=packet.id,
                seq_no=seq,
                filename=filename,
                content_type="image/jpeg",
                storage_key=storage_key,
                telegram_file_id=file_id,
                file_unique_id=file_unique_id,
                size_bytes=len(data),
            )
        )
        packet.photos_count = seq
        await session.commit()
    except Exception:
        logger.exception("Failed to save photo for user %s", user_id)
        await tg.send_message(
            chat_id,
            "Не удалось сохранить фото (сеть/VPN или Яндекс.Диск). Пришлите ещё раз и дождитесь «Фото N добавлено».",
            reply_markup=main_keyboard(),
        )
        return

    await tg.send_message(
        chat_id,
        f"Фото {seq} добавлено в пакет.",
        reply_markup=main_keyboard(),
    )


async def finish_packet(session: AsyncSession, tg: TelegramClient, user_id: int, chat_id: int) -> None:
    packet = (
        await session.scalars(
            select(Packet).where(Packet.telegram_user_id == user_id, Packet.status == "draft")
        )
    ).first()
    if not packet:
        await tg.send_message(chat_id, "Нет открытого пакета. Пришлите фото.", reply_markup=main_keyboard())
        return

    # Trust files table over cached counter (counter can lag after failed uploads)
    files_count = len(
        (
            await session.scalars(select(PacketFile).where(PacketFile.packet_id == packet.id))
        ).all()
    )
    if files_count < 1 and packet.photos_count < 1:
        await tg.send_message(
            chat_id,
            "В пакете нет сохранённых фото. Пришлите фото ещё раз (дождитесь «Фото N добавлено»), затем «Завершить пакет».",
            reply_markup=main_keyboard(),
        )
        return

    if packet.photos_count != files_count and files_count > 0:
        packet.photos_count = files_count

    packet.status = "queued"
    session.add(WorkerJob(packet_id=packet.id, job_type="recognize"))
    await session.commit()

    await tg.send_message(
        chat_id,
        f"Пакет принят в обработку ({packet.photos_count} фото).\nИщите результат в 1С (список ready).",
        reply_markup=main_keyboard(),
    )


async def handle_update(session: AsyncSession, payload: dict[str, Any]) -> None:
    tg = TelegramClient()

    callback = payload.get("callback_query")
    if callback:
        await _handle_callback(session, tg, callback)
        return

    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return

    user = message.get("from") or {}
    user_id = int(user["id"])
    chat_id = int(message["chat"]["id"])
    display = " ".join(x for x in [user.get("first_name"), user.get("last_name")] if x)
    await ensure_user(session, user_id, display or user.get("username"))

    text = (message.get("text") or "").strip()
    if text.startswith("/start") or text.startswith("/help"):
        await ensure_default_binding(session, user_id)
        await tg.send_message(
            chat_id,
            "Бот приёмки ТОРГ-12 / УПД.\n\n" + await context_text(session, user_id),
            reply_markup=main_keyboard(),
        )
        return

    if text.startswith("/context"):
        await tg.send_message(chat_id, await context_text(session, user_id), reply_markup=main_keyboard())
        return

    if text.startswith("/finish"):
        await finish_packet(session, tg, user_id, chat_id)
        return

    photos = message.get("photo")
    if photos:
        # largest size is last
        best = photos[-1]
        await add_photo_to_draft(
            session,
            tg,
            user_id,
            chat_id,
            best["file_id"],
            best.get("file_unique_id"),
        )
        return

    document = message.get("document")
    if document and str(document.get("mime_type", "")).startswith("image/"):
        await add_photo_to_draft(
            session,
            tg,
            user_id,
            chat_id,
            document["file_id"],
            document.get("file_unique_id"),
        )
        return

    if text:
        await tg.send_message(
            chat_id,
            "Пришлите фото документа или используйте кнопки.",
            reply_markup=main_keyboard(),
        )


async def _handle_callback(session: AsyncSession, tg: TelegramClient, callback: dict[str, Any]) -> None:
    data = callback.get("data") or ""
    user = callback.get("from") or {}
    user_id = int(user["id"])
    chat = callback.get("message", {}).get("chat") or {}
    chat_id = int(chat.get("id") or user_id)
    cq_id = callback["id"]

    display = " ".join(x for x in [user.get("first_name"), user.get("last_name")] if x)
    await ensure_user(session, user_id, display or user.get("username"))

    if data == "noop":
        await tg.answer_callback(cq_id)
        return

    if data == "context":
        await tg.answer_callback(cq_id)
        await tg.send_message(chat_id, await context_text(session, user_id), reply_markup=main_keyboard())
        return

    if data == "finish":
        # Ack immediately so Telegram stops the button spinner
        await tg.answer_callback(cq_id, "Обрабатываю…")
        await finish_packet(session, tg, user_id, chat_id)
        return

    if data == "pick_org":
        await tg.answer_callback(cq_id)
        await tg.send_message(chat_id, "Выберите организацию:", reply_markup=await orgs_keyboard(session))
        return

    if data == "pick_wh":
        binding = await get_binding(session, user_id)
        if not binding:
            await tg.answer_callback(cq_id, "Сначала организация")
            await tg.send_message(chat_id, "Выберите организацию:", reply_markup=await orgs_keyboard(session))
            return
        await tg.answer_callback(cq_id)
        await tg.send_message(chat_id, "Выберите склад:", reply_markup=await warehouses_keyboard(session, binding.org_id))
        return

    if data.startswith("org:"):
        org_id = data.split(":", 1)[1]
        whs = (
            await session.scalars(
                select(Warehouse).where(Warehouse.org_id == org_id, Warehouse.is_active.is_(True)).order_by(Warehouse.id)
            )
        ).all()
        await tg.answer_callback(cq_id, "Организация выбрана")
        if len(whs) == 1:
            await set_binding(session, user_id, org_id, whs[0].id)
            await tg.send_message(chat_id, await context_text(session, user_id), reply_markup=main_keyboard())
        else:
            # temporary bind org via first warehouse later; ask warehouse
            await tg.send_message(chat_id, "Выберите склад:", reply_markup=await warehouses_keyboard(session, org_id))
        return

    if data.startswith("wh:"):
        warehouse_id = data.split(":", 1)[1]
        wh = await session.get(Warehouse, warehouse_id)
        if not wh:
            await tg.answer_callback(cq_id, "Склад не найден")
            return
        await set_binding(session, user_id, wh.org_id, wh.id)
        await tg.answer_callback(cq_id, "Склад выбран")
        await tg.send_message(chat_id, await context_text(session, user_id), reply_markup=main_keyboard())
        return

    await tg.answer_callback(cq_id)

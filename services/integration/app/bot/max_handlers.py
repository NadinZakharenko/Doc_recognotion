"""MAX messenger handlers (pilot long-polling). Reuses packet/OCR pipeline."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import (
    context_text,
    ensure_default_binding,
    ensure_user,
    finish_packet,
    get_binding,
    main_keyboard,
    orgs_keyboard,
    save_photo_bytes_to_draft,
    set_binding,
    warehouses_keyboard,
)
from app.bot.max_api import MaxClient
from app.config import get_settings
from app.db.models import Warehouse

logger = logging.getLogger(__name__)


def _is_allowed(user_id: int) -> bool:
    settings = get_settings()
    whitelist = settings.channel_whitelist_ids
    if not whitelist:
        # Pilot discovery mode: allow, handlers will print user_id
        return True
    return user_id in whitelist


def _user_from_obj(user: dict[str, Any] | None) -> tuple[int | None, str | None]:
    if not user:
        return None, None
    uid = user.get("user_id") or user.get("id")
    if uid is None:
        return None, None
    name = user.get("name") or " ".join(
        x for x in [user.get("first_name"), user.get("last_name")] if x
    )
    return int(uid), (name.strip() or None)


def _chat_id_from_message(message: dict[str, Any], fallback_user_id: int) -> int:
    recipient = message.get("recipient") or {}
    chat_id = recipient.get("chat_id")
    if chat_id is not None:
        return int(chat_id)
    body_chat = (message.get("chat") or {}).get("chat_id")
    if body_chat is not None:
        return int(body_chat)
    return fallback_user_id


def _extract_image_attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    body = message.get("body") or message
    attachments = body.get("attachments") or message.get("attachments") or []
    images: list[dict[str, Any]] = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        atype = (att.get("type") or "").lower()
        if atype not in ("image", "photo", "file"):
            continue
        payload = att.get("payload") or {}
        url = payload.get("url") or att.get("url")
        if not url and atype == "file":
            # skip non-image files without url
            continue
        if not url:
            continue
        # For type=file require image-looking mime/name when present
        if atype == "file":
            name = str(payload.get("file_name") or payload.get("filename") or "").lower()
            mime = str(payload.get("mime_type") or "").lower()
            if mime and not mime.startswith("image/") and not name.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
                continue
        images.append(
            {
                "url": url,
                "token": str(payload.get("token") or payload.get("photo_id") or payload.get("id") or url),
                "unique": str(payload.get("photo_id") or payload.get("id") or ""),
            }
        )
    return images


async def handle_max_update(session: AsyncSession, bot: MaxClient, update: dict[str, Any]) -> None:
    update_type = update.get("update_type") or update.get("type") or ""

    if update_type == "bot_started":
        await _on_bot_started(session, bot, update)
        return

    if update_type == "message_callback":
        await _on_callback(session, bot, update)
        return

    if update_type == "message_created":
        await _on_message(session, bot, update)
        return

    logger.debug("Ignore MAX update_type=%s", update_type)


async def _on_bot_started(session: AsyncSession, bot: MaxClient, update: dict[str, Any]) -> None:
    user_id, display = _user_from_obj(update.get("user"))
    if user_id is None:
        return
    chat_id = int(update.get("chat_id") or user_id)

    if not _is_allowed(user_id):
        await bot.send_message(
            chat_id,
            f"Доступ закрыт. Ваш Max user_id={user_id}",
            user_id=user_id,
        )
        return

    await ensure_user(session, user_id, display)
    await ensure_default_binding(session, user_id)

    settings = get_settings()
    extra = ""
    if not settings.channel_whitelist_ids:
        extra = f"\n\nПилот: добавьте MAX_WHITELIST_IDS={user_id} в .env"

    await bot.send_message(
        chat_id,
        "Бот приёмки ТОРГ-12 / УПД (MAX).\n\n" + await context_text(session, user_id) + extra,
        reply_markup=main_keyboard(),
        user_id=user_id,
    )


async def _on_message(session: AsyncSession, bot: MaxClient, update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    sender = message.get("sender") or update.get("user") or {}
    user_id, display = _user_from_obj(sender)
    if user_id is None:
        return
    chat_id = _chat_id_from_message(message, user_id)

    if not _is_allowed(user_id):
        await bot.send_message(chat_id, f"Доступ закрыт. Ваш Max user_id={user_id}", user_id=user_id)
        return

    await ensure_user(session, user_id, display)

    body = message.get("body") or {}
    text = (body.get("text") or message.get("text") or "").strip()

    images = _extract_image_attachments(message)
    if images:
        for img in images:
            try:
                data = await bot.download_url(img["url"])
            except Exception:
                logger.exception("MAX image download failed")
                await bot.send_message(
                    chat_id,
                    "Не удалось скачать фото из MAX. Пришлите ещё раз.",
                    reply_markup=main_keyboard(),
                    user_id=user_id,
                )
                continue
            await save_photo_bytes_to_draft(
                session,
                bot,
                user_id,
                chat_id,
                data,
                file_token=img.get("token"),
                file_unique_id=img.get("unique") or None,
                user_id_for_send=user_id,
            )
        return

    if text.lower() in {"/start", "start", "/help", "help"}:
        await ensure_default_binding(session, user_id)
        await bot.send_message(
            chat_id,
            "Бот приёмки ТОРГ-12 / УПД (MAX).\n\n" + await context_text(session, user_id),
            reply_markup=main_keyboard(),
            user_id=user_id,
        )
        return

    if text.lower() in {"/finish", "finish", "завершить"}:
        await finish_packet(session, bot, user_id, chat_id, user_id_for_send=user_id)
        return

    if text.lower() in {"/context", "context"}:
        await bot.send_message(
            chat_id,
            await context_text(session, user_id),
            reply_markup=main_keyboard(),
            user_id=user_id,
        )
        return

    if text:
        await bot.send_message(
            chat_id,
            "Пришлите фото документа или используйте кнопки.",
            reply_markup=main_keyboard(),
            user_id=user_id,
        )


async def _on_callback(session: AsyncSession, bot: MaxClient, update: dict[str, Any]) -> None:
    callback = update.get("callback") or {}
    user_id, display = _user_from_obj(callback.get("user") or update.get("user"))
    if user_id is None:
        return

    message = update.get("message") or callback.get("message") or {}
    chat_id = _chat_id_from_message(message, user_id) if message else int(update.get("chat_id") or user_id)
    cq_id = str(callback.get("callback_id") or callback.get("id") or "")
    data = str(callback.get("payload") or callback.get("data") or "")

    if not _is_allowed(user_id):
        if cq_id:
            await bot.answer_callback(cq_id, "Нет доступа")
        return

    await ensure_user(session, user_id, display)

    if data == "noop":
        if cq_id:
            await bot.answer_callback(cq_id)
        return

    if data == "context":
        if cq_id:
            await bot.answer_callback(cq_id)
        await bot.send_message(
            chat_id,
            await context_text(session, user_id),
            reply_markup=main_keyboard(),
            user_id=user_id,
        )
        return

    if data == "finish":
        if cq_id:
            await bot.answer_callback(cq_id, "Обрабатываю…")
        await finish_packet(session, bot, user_id, chat_id, user_id_for_send=user_id)
        return

    if data == "pick_org":
        if cq_id:
            await bot.answer_callback(cq_id)
        await bot.send_message(
            chat_id,
            "Выберите организацию:",
            reply_markup=await orgs_keyboard(session),
            user_id=user_id,
        )
        return

    if data == "pick_wh":
        binding = await get_binding(session, user_id)
        if not binding:
            if cq_id:
                await bot.answer_callback(cq_id, "Сначала организация")
            await bot.send_message(
                chat_id,
                "Выберите организацию:",
                reply_markup=await orgs_keyboard(session),
                user_id=user_id,
            )
            return
        if cq_id:
            await bot.answer_callback(cq_id)
        await bot.send_message(
            chat_id,
            "Выберите склад:",
            reply_markup=await warehouses_keyboard(session, binding.org_id),
            user_id=user_id,
        )
        return

    if data.startswith("org:"):
        org_id = data.split(":", 1)[1]
        whs = (
            await session.scalars(
                select(Warehouse).where(Warehouse.org_id == org_id, Warehouse.is_active.is_(True)).order_by(Warehouse.id)
            )
        ).all()
        if cq_id:
            await bot.answer_callback(cq_id, "Организация выбрана")
        if len(whs) == 1:
            await set_binding(session, user_id, org_id, whs[0].id)
            await bot.send_message(
                chat_id,
                await context_text(session, user_id),
                reply_markup=main_keyboard(),
                user_id=user_id,
            )
        else:
            await bot.send_message(
                chat_id,
                "Выберите склад:",
                reply_markup=await warehouses_keyboard(session, org_id),
                user_id=user_id,
            )
        return

    if data.startswith("wh:"):
        warehouse_id = data.split(":", 1)[1]
        wh = await session.get(Warehouse, warehouse_id)
        if not wh:
            if cq_id:
                await bot.answer_callback(cq_id, "Склад не найден")
            return
        await set_binding(session, user_id, wh.org_id, wh.id)
        if cq_id:
            await bot.answer_callback(cq_id, "Склад выбран")
        await bot.send_message(
            chat_id,
            await context_text(session, user_id),
            reply_markup=main_keyboard(),
            user_id=user_id,
        )
        return

    if cq_id:
        await bot.answer_callback(cq_id)

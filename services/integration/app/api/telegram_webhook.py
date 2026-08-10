"""Telegram webhook endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.dialects.postgresql import insert

from app.bot.handlers import handle_update
from app.config import get_settings
from app.db.models import TelegramUpdate
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telegram"])


def _is_allowed(user_id: int) -> bool:
    settings = get_settings()
    whitelist = settings.whitelist_ids
    if not whitelist:
        logger.warning("TELEGRAM_WHITELIST_IDS empty — all users rejected")
        return False
    return user_id in whitelist


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    payload: dict[str, Any] = await request.json()
    update_id = payload.get("update_id")
    if update_id is None:
        return {"status": "ignored"}

    message = payload.get("message") or payload.get("edited_message") or {}
    user = message.get("from") or {}
    user_id = user.get("id")
    callback = payload.get("callback_query") or {}
    if user_id is None and callback:
        user_id = (callback.get("from") or {}).get("id")

    if user_id is None:
        return {"status": "ignored"}

    if not _is_allowed(int(user_id)):
        logger.info("Rejected non-whitelist user %s", user_id)
        return {"status": "forbidden"}

    async with SessionLocal() as session:
        stmt = insert(TelegramUpdate).values(update_id=int(update_id)).on_conflict_do_nothing()
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount == 0:
            return {"status": "duplicate"}

        try:
            await handle_update(session, payload)
        except Exception:
            logger.exception("Failed to handle update %s", update_id)
            return {"status": "error"}

    return {"status": "ok"}

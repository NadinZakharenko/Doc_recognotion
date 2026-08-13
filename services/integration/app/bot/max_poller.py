"""MAX long-polling runner for pilot (no ngrok / no foreign VPN)."""

from __future__ import annotations

import asyncio
import logging
import sys

from app.bot.max_api import MaxClient
from app.bot.max_handlers import handle_max_update
from app.config import get_settings
from app.db.session import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("max_poller")

UPDATE_TYPES = [
    "message_created",
    "message_callback",
    "bot_started",
]


async def run_forever() -> None:
    settings = get_settings()
    if (settings.bot_channel or "").lower() != "max":
        logger.warning("BOT_CHANNEL=%s — max poller expected BOT_CHANNEL=max", settings.bot_channel)
    if not settings.max_bot_token:
        raise RuntimeError("MAX_BOT_TOKEN is empty")

    bot = MaxClient(settings)
    me = await bot.get_me()
    logger.info(
        "MAX poller started as %s (@%s) user_id=%s base=%s",
        me.get("name") or me.get("first_name"),
        me.get("username") or settings.max_bot_username,
        me.get("user_id"),
        settings.max_api_base_url,
    )

    removed = await bot.clear_webhook_subscriptions()
    if removed:
        logger.info("Cleared %s webhook subscription(s) to enable long polling", removed)

    marker: int | None = None
    timeout = int(settings.max_poll_timeout or 30)
    limit = int(settings.max_poll_limit or 100)

    while True:
        try:
            data = await bot.get_updates(
                marker=marker,
                limit=limit,
                timeout=timeout,
                types=UPDATE_TYPES,
            )
        except Exception:
            logger.exception("get_updates failed; sleep 3s")
            await asyncio.sleep(3)
            continue

        updates = data.get("updates") or []
        next_marker = data.get("marker")
        if next_marker is not None:
            try:
                marker = int(next_marker)
            except (TypeError, ValueError):
                pass

        if not updates:
            continue

        for update in updates:
            if not isinstance(update, dict):
                continue
            try:
                async with SessionLocal() as session:
                    await handle_max_update(session, bot, update)
            except Exception:
                logger.exception("Failed to handle MAX update %s", update.get("update_type"))


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()

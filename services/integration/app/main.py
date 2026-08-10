import logging

from fastapi import FastAPI

from app.api import health, packets, telegram_webhook
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Doc Recognition Integration API",
    version="0.1.0",
    description="Telegram → storage → OCR → 1C (MVP)",
)

app.include_router(health.router)
app.include_router(packets.router)
app.include_router(telegram_webhook.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "doc-recognition", "env": settings.app_env}

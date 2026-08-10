from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    log_level: str = "INFO"
    api_bearer_token: str = "change-me-1c-token"

    database_url: str = "postgresql+asyncpg://docrec:docrec@localhost:5432/docrec"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = "change-me-webhook-secret"
    telegram_whitelist_ids: str = ""
    telegram_webhook_base_url: str = ""

    storage_backend: str = "local"  # local | yandex
    local_storage_root: str = "./data/packets"
    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    yandex_refresh_token: str = ""
    yandex_disk_root: str = "/Приходные накладные"

    ocr_mode: str = "yandexgpt"  # stub | openai | grok | yandexgpt | anydoc
    ocr_api_url: str = ""
    ocr_api_key: str = ""
    openai_api_key: str = ""
    openai_vision_model: str = "gpt-4o"
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_vision_model: str = "grok-4"
    # Yandex Cloud Foundation Models + Vision OCR
    yandex_cloud_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_gpt_model: str = "yandexgpt/latest"
    yandex_ocr_model: str = "table"  # page | table | handwritten
    yandex_recognize_mode: str = "ocr_gpt"  # ocr_gpt | vision (gemma)
    yandex_vision_model: str = "gemma-3-27b-it/latest"
    firecrawl_api_key: str = ""

    worker_poll_seconds: float = 2.0
    worker_id: str = "worker-1"

    @property
    def whitelist_ids(self) -> set[int]:
        if not self.telegram_whitelist_ids.strip():
            return set()
        return {int(x.strip()) for x in self.telegram_whitelist_ids.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

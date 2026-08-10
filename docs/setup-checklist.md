# Чеклист запуска пилота: BotFather + туннель + Yandex OAuth + БД

Отмечайте пункты по мере выполнения. Секреты только в `.env` (из `.env.example`).

---

## 1. Telegram-бот (новый)

1. В Telegram открыть [@BotFather](https://t.me/BotFather)
2. `/newbot` → имя и username (например `RWB Doc Pilot` / `rwb_doc_pilot_bot`)
3. Скопировать **token** → `TELEGRAM_BOT_TOKEN` в `.env`
4. `/setjoingrouproups` → Disable (только личка)
5. Написать боту `/start` с пилотного аккаунта
6. Узнать свой id: [@userinfobot](https://t.me/userinfobot) или аналог → `TELEGRAM_WHITELIST_IDS=<id>`
7. В БД после первого старта (или вручную):

```sql
INSERT INTO users (telegram_user_id, display_name, is_whitelisted)
VALUES (<id>, 'Pilot', TRUE)
ON CONFLICT (telegram_user_id) DO UPDATE SET is_whitelisted = TRUE;

INSERT INTO user_bindings (telegram_user_id, org_id, warehouse_id)
VALUES (<id>, 'org-001', 'wh-001')
ON CONFLICT (telegram_user_id) DO UPDATE
SET org_id = EXCLUDED.org_id, warehouse_id = EXCLUDED.warehouse_id;
```

8. Придумать секрет webhook → `TELEGRAM_WEBHOOK_SECRET`

---

## 2. Туннель (пилот) — ngrok

```powershell
ngrok http 8080
```

HTTPS URL → `TELEGRAM_WEBHOOK_BASE_URL=https://....ngrok-free.app` (или `*.ngrok-free.dev`).

Затем зарегистрировать webhook:

```powershell
$token = $env:TELEGRAM_BOT_TOKEN
$base = $env:TELEGRAM_WEBHOOK_BASE_URL
$secret = $env:TELEGRAM_WEBHOOK_SECRET
Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/setWebhook" -Body @{
  url = "$base/telegram/webhook"
  secret_token = $secret
  drop_pending_updates = $true
}
Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo"
```

Или скрипт: `scripts/set_telegram_webhook.ps1`

---

## 3. Yandex Disk (личный 360)

1. Создать приложение: [oauth.yandex.ru](https://oauth.yandex.ru/) → «Создать новое приложение»
2. Платформы: **Веб-сервисы**; Redirect URI для отладки: `https://oauth.yandex.ru/verification_code`
3. Доступы Disk:  
   - `cloud_api:disk.read`  
   - `cloud_api:disk.write`  
   - `cloud_api:disk.app_folder` (опционально)
4. Скопировать `ClientID` / `Client secret` → `YANDEX_CLIENT_ID` / `YANDEX_CLIENT_SECRET`
5. Получить код (в браузере, под пилотным Яндекс-аккаунтом):

```text
https://oauth.yandex.ru/authorize?response_type=code&client_id=<CLIENT_ID>
```

6. Обменять code на tokens:

```powershell
Invoke-RestMethod -Method Post -Uri "https://oauth.yandex.ru/token" -Body @{
  grant_type = "authorization_code"
  code = "<CODE>"
  client_id = $env:YANDEX_CLIENT_ID
  client_secret = $env:YANDEX_CLIENT_SECRET
}
```

7. Сохранить `refresh_token` → `YANDEX_REFRESH_TOKEN`
8. В `.env`: `STORAGE_BACKEND=yandex` (для старта без OAuth оставить `local`)
9. Корень: `YANDEX_DISK_ROOT=/Приходные накладные`

Проверка вручную (после появления access_token): создать папку через Disk API `PUT /v1/disk/resources?path=...`.

### 3b. YandexGPT + Vision OCR (не Disk OAuth)

Нужны ключи **Yandex Cloud** (отдельные от Диска):

1. [console.yandex.cloud](https://console.yandex.cloud) → каталог → скопировать **Folder ID** → `YANDEX_FOLDER_ID`
2. Сервисный аккаунт с ролями `ai.languageModels.user` + `ai.vision.user` (или `editor` на каталог)
3. Создать **API-ключ** → `YANDEX_CLOUD_API_KEY`
4. В `.env`: `OCR_MODE=yandexgpt`, `YANDEX_RECOGNIZE_MODE=ocr_gpt` (Vision OCR → YandexGPT → JSON)

Проверка: `python scripts/recognize_sample.py` из `services/integration`.

---

## 4. Локальный запуск сервиса

```powershell
cd C:\AI\Doc_recognotion
Copy-Item .env.example .env
# заполнить TELEGRAM_*, API_BEARER_TOKEN; STORAGE_BACKEND=local для первого прогона

docker compose up -d --build
curl http://localhost:8080/health
```

API для 1С (пример):

```powershell
$h = @{ Authorization = "Bearer change-me-1c-token" }
Invoke-RestMethod -Headers $h "http://localhost:8080/api/v1/packets?status=ready"
```

OpenAPI-контракт: `specs/openapi.yaml`.

---

## 5. Порядок готовности

| Шаг | Статус |
|-----|--------|
| `.env` из example | ✅ |
| BotFather token + whitelist `322646729` | ✅ |
| Postgres `docrec` + DDL + seed | ✅ |
| API + worker локально (без Docker) | ✅ |
| Туннель ngrok + setWebhook | ✅ (пилот; Cloudflare не используем) |
| Handlers бота (org/склад/фото/завершить) | ✅ |
| Yandex OAuth | ✅ |
| Образцы фото | ✅ первый ТОРГ-12 в `samples/torg12/` |
| Внешний OCR | ✅ авто-OCR: **Yandex Vision OCR → YandexGPT** (`OCR_MODE=yandexgpt`) |

---

## Полезные пути

| Путь | Назначение |
|------|------------|
| `services/integration/` | Код API + worker |
| `services/integration/migrations/001_init.sql` | DDL |
| `docker-compose.yml` | Postgres + api + worker |
| `docs/mvp-overview.md` | Зафиксированный MVP |
| `specs/` | result schema + OpenAPI |

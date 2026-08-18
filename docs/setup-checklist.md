# Чеклист запуска пилота: MAX-бот (long polling) + Yandex OAuth + БД

Отмечайте пункты по мере выполнения. Секреты только в `.env` (из `.env.example`).

---

## 1. MAX-бот (пилот, без ngrok / без иностранного VPN)

1. Создать бота в [MAX для разработчиков](https://dev.max.ru/docs-api) / «MAX для бизнеса»
2. Скопировать **access token** → `MAX_BOT_TOKEN` в `.env`
3. Зафиксировать имя/ник (пример пилота: `VZ_Test_Bot` / `se13938479_bot`) → `MAX_BOT_USERNAME`
4. В `.env`: `BOT_CHANNEL=max`
5. Запуск long polling (webhook не нужен):

```powershell
cd C:\AI\Doc_recognotion
.\scripts\run-max-poller.ps1
```

6. Написать боту в MAX → бот ответит и покажет ваш `user_id`, если whitelist пуст
7. Прописать `MAX_WHITELIST_IDS=<id>` и перезапустить poller
8. В БД (после первого сообщения или вручную):

```sql
INSERT INTO users (telegram_user_id, display_name, is_whitelisted)
VALUES (<max_user_id>, 'Pilot', TRUE)
ON CONFLICT (telegram_user_id) DO UPDATE SET is_whitelisted = TRUE;

INSERT INTO user_bindings (telegram_user_id, org_id, warehouse_id)
VALUES (<max_user_id>, 'org-001', 'wh-001')
ON CONFLICT (telegram_user_id) DO UPDATE
SET org_id = EXCLUDED.org_id, warehouse_id = EXCLUDED.warehouse_id;
```

> Колонка `telegram_user_id` в пилоте хранит id пользователя **канала** (сейчас MAX). Переименование в `messenger_user_id` — после пилота.

Параллельно нужны API + OCR worker:

```powershell
.\scripts\run-local.ps1
```

### Ограничения транспорта

- Пилот: **long polling** (`GET /updates`) — без публичного HTTPS
- Webhook MAX требует HTTPS `:443` и доверенный сертификат; ngrok / иностранный VPN **не используем**
- Long polling и webhook одновременно нельзя; poller при старте снимает webhook-подписки

---

## 1b. Telegram (legacy, только если BOT_CHANNEL=telegram)

1. В Telegram открыть [@BotFather](https://t.me/BotFather)
2. `/newbot` → имя и username
3. Token → `TELEGRAM_BOT_TOKEN`
4. Нужен публичный HTTPS webhook (ngrok и т.п.) — **не для текущего пилота без VPN**

---

## 3. Локальная папка для входящих документов

1. Создать папку `C:\Test\incoming_invoices`
2. Убедиться, что у пользователя, под которым запущен сервис, есть права на чтение/запись
3. В `.env` указать:

```text
STORAGE_BACKEND=local
LOCAL_STORAGE_ROOT=C:\Test\incoming_invoices
```

4. Структура внутри папки создаётся автоматически:

```text
<org_id>/<warehouse_id>/<user_label>/<YYYY-MM-DD>/<packet_id>/images/
```

5. Проверка вручную: отправить фото в бот и убедиться, что в `C:\Test\incoming_invoices` появилась новая ветка каталога с `images/`

### 3b. YandexGPT + Vision OCR

Нужны ключи **Yandex Cloud**:

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
# заполнить MAX_*, API_BEARER_TOKEN и Yandex Cloud OCR

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
| MAX-бот `VZ_Test_Bot` / `se13938479_bot` + long polling | ✅ пилот |
| Postgres `docrec` + DDL + seed | ✅ |
| API + worker локально (без Docker) | ✅ |
| Туннель ngrok | ❌ не используем (нет иностранного VPN) |
| Handlers бота (org/склад/фото/завершить) | ✅ MAX + legacy Telegram |
| Yandex OAuth | ✅ |
| Образцы фото | ✅ первый ТОРГ-12 в `samples/torg12/` |
| Внешний OCR | ✅ авто-OCR: **Yandex Vision OCR → YandexGPT** (`OCR_MODE=yandexgpt`) |

---

## Полезные пути

| Путь | Назначение |
|------|------------|
| `scripts/run-max-poller.ps1` | MAX long polling (пилот) |
| `services/integration/` | Код API + worker |
| `services/integration/migrations/001_init.sql` | DDL |
| `docker-compose.yml` | Postgres + api + worker |
| `docs/mvp-overview.md` | Зафиксированный MVP |
| `specs/` | result schema + OpenAPI |

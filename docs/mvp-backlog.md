# MVP backlog: Telegram → OCR → 1С (ТОРГ-12 / УПД)

Обзор: [`mvp-overview.md`](mvp-overview.md).

Пилот: **1 пользователь**, новый бот, webhook через **туннель**, **Yandex Disk** (персональные каталоги), fallback **local/SMB**, в 1С — **ручной refresh и выбор пакета**.

---

## Итерация 0 — доступы (параллельно)

Чеклист: [`setup-checklist.md`](setup-checklist.md)

- [ ] Создать Telegram-бота (@BotFather), сохранить token в secrets
- [ ] Зафиксировать whitelist: один `telegram_user_id`
- [ ] Поднять туннель (ngrok/cloudflared) → HTTPS webhook (`scripts/set_telegram_webhook.ps1`)
- [ ] Зарегистрировать OAuth-приложение Яндекс, получить refresh token личного 360
- [ ] Проверить upload/create folder в Yandex Disk API
- [ ] Дождаться образцов ТОРГ-12/УПД (запрошены)
- [ ] `Copy-Item .env.example .env` + `docker compose up -d --build`
- [ ] Подготовить каталог fallback local (`STORAGE_BACKEND=local`)

---

## Итерация 1 — каркас (бот + БД + диск)

### Бот Telegram
- [ ] Webhook + проверка секрета; отказ всем, кроме whitelist
- [ ] Org / склад, «Завершить пакет», «Мой контекст»
- [ ] Фото / media group → `draft`
- [ ] Ответы: «фото N добавлено», «принято, ищите в 1С»
- [ ] Без push ready / error / imported

### СУБД / хранилище
- [ ] PostgreSQL: users, orgs, warehouses, bindings, packets, packet_files
- [ ] Адаптер `YandexDiskStorage` + `LocalStorage` (переключение конфигом)
- [ ] Путь: `/Приходные накладные/<org>/<warehouse>/<user>/<date>/<packet_id>/`
- [ ] Миграции + seed одной org/склада

### Сервис
- [ ] `/health`, webhook, `draft → queued`
- [ ] Stub: `queued → ready` + фикстурный `result.json`

**DoD:** один пользователь собирает пакет; файлы на Yandex (или local); статус `ready` в БД.

---

## Итерация 2 — OCR + API для 1С

- [ ] Очередь OCR, внешний Vision/LLM, валидация schema
- [ ] `result.json` на диск; `ready | error`
- [ ] `GET /packets`, `GET .../result`, `POST .../imported` + Bearer
- [ ] Без статусных пушей в Telegram

**DoD:** Postman/1С-консоль видит `ready` и читает result.

---

## Итерация 3 — 1С:ERP (минимально)

- [ ] HTTP-клиент к API
- [ ] Форма: **Обновить** → список `ready`
- [ ] **Ручной выбор** пакета (без автофильтра прав)
- [ ] Просмотр полей / создание черновика ПТиУ
- [ ] `imported` с `ptu_ref`

**DoD:** полный путь без уведомлений в Telegram.

---

## Вне скоупа

- Много пользователей, роли, регламент 1С
- MAX/Band, Google Drive как primary
- Push UX 4–5, интерактив дублей в боте
- Автопроведение, маппинг Telegram↔1С

---

## Риски

| Риск | Митигация |
|------|-----------|
| Туннель нестабилен | Документировать URL; позже постоянный HTTPS |
| OAuth личного Yandex | Secrets + refresh; fallback local |
| Нет образцов | Ждём запрошенные фото; stub result до них |
| Ручной выбор в 1С | Ок для 1 пользователя; фильтры — пост-MVP |

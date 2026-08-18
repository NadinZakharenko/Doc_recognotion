# MVP backlog: MAX → OCR → 1С (ТОРГ-12 / УПД)

Обзор: [`mvp-overview.md`](mvp-overview.md).

Пилот: **1 пользователь**, MAX-бот, **long polling**, локальная папка `C:\Test\incoming_invoices`, в 1С — **ручной refresh и выбор пакета**.

---

## Итерация 0 — доступы (параллельно)

Чеклист: [`setup-checklist.md`](setup-checklist.md)

- [ ] Создать MAX-бота, сохранить token в secrets
- [ ] Зафиксировать whitelist: один `telegram_user_id`
- [ ] Проверить long polling MAX
- [ ] Создать локальную папку `C:\Test\incoming_invoices`
- [ ] Дождаться образцов ТОРГ-12/УПД (запрошены)
- [ ] `Copy-Item .env.example .env` + `docker compose up -d --build`
- [ ] Проверить права на чтение/запись в `C:\Test\incoming_invoices`

---

## Итерация 1 — каркас (бот + БД + диск)

### Бот MAX
- [ ] Long polling; отказ всем, кроме whitelist
- [ ] Org / склад, «Завершить пакет», «Мой контекст»
- [ ] Фото / media group → `draft`
- [ ] Ответы: «фото N добавлено», «принято, ищите в 1С»
- [ ] Без push ready / error / imported

### СУБД / хранилище
- [ ] PostgreSQL: users, orgs, warehouses, bindings, packets, packet_files
- [ ] Адаптер `LocalStorage`
- [ ] Путь: `C:\Test\incoming_invoices\<org>\<warehouse>\<user>\<date>\<packet_id>\`
- [ ] Миграции + seed одной org/склада

### Сервис
- [ ] `/health`, webhook, `draft → queued`
- [ ] Stub: `queued → ready` + фикстурный `result.json`

**DoD:** один пользователь собирает пакет; файлы в локальной папке; статус `ready` в БД.

---

## Итерация 2 — OCR + API для 1С

- [ ] Очередь OCR, внешний Vision/LLM, валидация schema
- [ ] `result.json` в локальную папку; `ready | error`
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

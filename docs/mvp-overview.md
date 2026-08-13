# MVP (зафиксированный): Telegram → OCR → 1С

Канал: **Telegram**. Документы: **ТОРГ-12 / УПД**. Выход: **`result.json`**.  
Хранилище: **Yandex Disk** (личные каталоги), fallback: локальный диск/SMB.  
Правки только в 1С. Excel и превью в чате нет.

---

## Зафиксированные решения пилота

| # | Тема | Решение |
|---|------|---------|
| 1 | Telegram-бот | **Создать новый** (@BotFather) |
| 2 | Webhook | Пока **туннель** (Cloudflare Tunnel / ngrok и т.п.) |
| 3 | Доступ к боту | **Один** `telegram_user_id` (whitelist) |
| 4 | Yandex | Личный **Яндекс 360**, OAuth этого аккаунта |
| 5 | Структура папок | Как в концепте — **персональные каталоги** |
| 6 | ИБ | ОК на Yandex Disk + внешний OCR/LLM на старте |
| 7 | Список в 1С | Оператор **сам обновляет** (кнопка), без регламента |
| 8 | Выбор в 1С | **Вручную** (пакет/папка), без автофильтра по правам |
| 9 | Fallback storage | **Да** — локальный диск/SMB, тот же API |
| 10 | Образцы | **Запрошены** (ожидаем 20–50 фото) |

---

## Поток MVP

```text
1 пользователь Telegram (whitelist)
  → org / склад
  → фото страниц
  → «Завершить пакет»
  → Yandex Disk (персональный путь) + PostgreSQL
  → OCR (внешний API) → result.json
  → status = ready
  → 1С: кнопка обновить → ручной выбор пакета/папки
  → черновик ПТиУ → POST .../imported
```

### UX бота

| # | Шаг | MVP |
|---|-----|-----|
| 1 | Org / склад | да |
| 2 | Фото → «фото N добавлено» | да |
| 3 | «Завершить пакет» → «принято, ищите в 1С» | да |
| 4 | Push ready / error | **нет** |
| 5 | Push imported | **нет** |

---

## Архитектура

| Узел | Решение |
|------|---------|
| Канал | Новый Telegram-бот, webhook через туннель |
| ACL бота | Whitelist: 1 user id |
| Сервис | On-prem RWB |
| Реестр | PostgreSQL |
| Файлы | Yandex Disk API (личный 360); адаптер + fallback local/SMB |
| OCR | Внешний Vision/LLM |
| 1С | Pull по кнопке, ручной выбор пакета, ручной ПТиУ |

```text
Telegram (tunnel → webhook)
  → Bot service
       ├─ PostgreSQL
       ├─ Yandex Disk / local storage
       └─ OCR worker
1С:ERP ← HTTP API (list / result / imported)
         оператор сам Refresh + выбирает пакет вручную
```

---

## Пути на Yandex Disk (как в концепте)

```text
/incoming_invoices/
  /<org_id>/
    /<warehouse_id>/
      /<user_label>/
        /<Дата YYYY-MM-DD>/
          /<packet_id>/
            /images/
              001.jpg
              002.jpg
            result.json
```

Для пилота с одним пользователем ветка `<Пользователь>/` всё равно создаётся — проще масштабировать позже.  
В БД хранятся `packet_id`, статус и `storage_path`; 1С работает через API, но UI MVP допускает **ручной выбор** пакета (по сути выбор записи/папки из списка).

---

## 1С (упрощение пилота)

- Кнопка «Обновить список» (без регламентного задания).
- Список пакетов `ready` (можно показать все для пилота — один пользователь).
- Оператор **вручную** выбирает нужный пакет.
- Создаёт черновик ПТиУ вручную / полуавтоматом из `result.json`.
- Вызывает `imported`.

Автофильтрация по пользователю 1С / площадке — **после MVP**.

---

## Контракты

- `specs/result.schema.json` — `telegram_user_id`
- `specs/openapi.yaml` — `list` / `result` / `imported`
- Storage за интерфейсом адаптера: `YandexDiskStorage` | `LocalStorage`

---

## Вне скоупа MVP

- MAX / Band, Google Drive как основной диск
- Push-статусы в Telegram
- Многопользовательский ACL, маппинг Telegram↔1С
- Регламент обновления в 1С, автопроведение
- Интерактив «требует действия» в боте

---

## Блокеры до полноценного UX бота

1. Итерация 0 по [`setup-checklist.md`](setup-checklist.md): бот, туннель, whitelist, `.env`, `docker compose`.
2. OAuth Яндекс Disk (до этого `STORAGE_BACKEND=local`).
3. Образцы фото (уже запрошены).
4. Дописать handlers в `app/api/telegram_webhook.py` (org/склад/фото/завершить).

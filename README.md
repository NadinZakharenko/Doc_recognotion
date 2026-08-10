# Doc recognition (Telegram → OCR → 1С)

Пилот RWB: товаровед фотографирует ТОРГ-12/УПД в **Telegram**, сервис сохраняет пакет на **Yandex Disk** (или local), распознаёт документ и отдаёт `result.json` в **1С:ERP**.

## Быстрый старт

```powershell
Copy-Item .env.example .env
docker compose up -d --build
curl http://localhost:8080/health
```

Чеклист BotFather / туннель / Yandex: [`docs/setup-checklist.md`](docs/setup-checklist.md)

## Документы MVP

| Путь | Описание |
|------|----------|
| [`docs/mvp-overview.md`](docs/mvp-overview.md) | Зафиксированный MVP |
| [`docs/mvp-backlog.md`](docs/mvp-backlog.md) | Backlog по итерациям |
| [`docs/setup-checklist.md`](docs/setup-checklist.md) | Доступы и запуск |
| [`specs/result.schema.json`](specs/result.schema.json) | JSON Schema результата |
| [`specs/openapi.yaml`](specs/openapi.yaml) | HTTP API для 1С |
| [`services/integration/`](services/integration/) | Код сервиса + DDL |

## Краткие решения MVP

- Канал: новый Telegram-бот, webhook через туннель, **1 пользователь** (whitelist)
- Хранилище: Yandex Disk (личный 360, персональные каталоги); fallback local/SMB
- UX бота: org/склад + фото + «Завершить пакет»; без push ready/imported
- 1С: кнопка обновить, **ручной выбор** пакета, ручной черновик ПТиУ
- Образцы ТОРГ-12/УПД: запрошены

Исторические материалы (архитектура MAX, концепт Band/RWBdisk) оставлены в корне для справки.

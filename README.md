# Doc recognition (MAX → OCR → 1С)

Пилот RWB: товаровед фотографирует ТОРГ-12/УПД в **MAX**, сервис сохраняет пакет на **Yandex Disk** (или local), распознаёт документ и отдаёт `result.json` в **1С:ERP**.

## Быстрый старт (пилот без ngrok)

```powershell
Copy-Item .env.example .env
# заполнить MAX_BOT_TOKEN, DATABASE_URL, OCR/Yandex при необходимости
# BOT_CHANNEL=max

# API + OCR worker
.\scripts\run-local.ps1

# MAX long polling (отдельное окно)
.\scripts\run-max-poller.ps1
```

Чеклист: [`docs/setup-checklist.md`](docs/setup-checklist.md)

## Документы MVP

| Путь | Описание |
|------|----------|
| [`docs/mvp-overview.md`](docs/mvp-overview.md) | Зафиксированный MVP |
| [`docs/mvp-backlog.md`](docs/mvp-backlog.md) | Backlog по итерациям |
| [`docs/setup-checklist.md`](docs/setup-checklist.md) | Доступы и запуск |
| [`docs/mvp-process.drawio`](docs/mvp-process.drawio) | Схема процесса |
| [`specs/result.schema.json`](specs/result.schema.json) | JSON Schema результата |
| [`specs/openapi.yaml`](specs/openapi.yaml) | HTTP API для 1С |
| [`services/integration/`](services/integration/) | Код сервиса + DDL |

## Краткие решения пилота

- Канал: **MAX** (`VZ_Test_Bot` / `se13938479_bot`), транспорт **long polling** (без иностранного VPN / ngrok)
- Хранилище: Yandex Disk (личный 360); fallback local
- UX бота: org/склад + фото + «Завершить пакет»; без push ready/imported
- 1С: кнопка обновить, ручной выбор пакета, ручной черновик ПТиУ
- OCR: Yandex Vision OCR → YandexGPT

# Doc recognition (MAX → OCR → 1С)

Интеграционный контур для RWB: бот MAX принимает фото ТОРГ-12/УПД, сервис распознаёт документ и отдаёт `result.json` в 1С:ERP для ручного создания черновика ПТиУ.

## Документы

| Путь | Описание |
|------|----------|
| `docs/mvp-backlog.md` | Backlog MVP по итерациям |
| `specs/result.schema.json` | JSON Schema результата распознавания |
| `specs/result.example.json` | Пример `result.json` |
| `specs/openapi.yaml` | HTTP API для 1С (`list` / `result` / `imported`) |
| `max_1c_architecture.drawio` | Архитектурная схема |
| `Архитектурная схема взаимодействия MAX с 1С через.md` | Описание архитектуры |
| `Концепт-дизайн_автоматизация_ПТиУ_по_фото_RWB.docx` | Концепт-дизайн |

## Статус

Проектирование MVP. Реализация бота и сервисов — по `docs/mvp-backlog.md`.

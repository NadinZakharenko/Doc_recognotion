# Integration service (MAX → local storage → OCR → 1C API)

## Quick start

From repo root:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
curl http://localhost:8080/health
```

Setup checklist: [`../../docs/setup-checklist.md`](../../docs/setup-checklist.md)

## Layout

```text
app/
  main.py                 # FastAPI
  config.py               # settings from env
  api/
    health.py
    packets.py            # 1C API (list/result/imported)
    telegram_webhook.py   # webhook + whitelist (handlers stub)
  db/
    models.py
    session.py
  storage/
    local.py              # active storage backend for MVP_Max_Local
    yandex.py             # legacy adapter
  worker/
    runner.py             # queue + stub OCR
migrations/
  001_init.sql
```

## Notes

- Default `STORAGE_BACKEND=local`, root `C:\Test\incoming_invoices`.
- `OCR_MODE=stub` until samples + external OCR in iteration 2.
- Bot photo/org handlers are stubs — whitelist + idempotent updates work.

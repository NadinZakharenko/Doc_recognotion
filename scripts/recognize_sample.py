"""Smoke-test OCR on samples/torg12/torg12_example_01.png"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "integration"))

from app.config import get_settings  # noqa: E402
from app.ocr.pipeline import recognize_packet_files  # noqa: E402


async def main() -> None:
    sample = ROOT / "samples" / "torg12" / "torg12_example_01.png"
    settings = get_settings()
    print("ocr_mode", settings.ocr_mode)
    print("yandex_mode", settings.yandex_recognize_mode)
    print("yandex_key", "yes" if settings.yandex_cloud_api_key else "NO")
    print("folder", settings.yandex_folder_id or "NO")
    result = await recognize_packet_files(
        settings,
        [{"filename": sample.name, "content_type": "image/png", "data": sample.read_bytes()}],
    )
    out = {k: v for k, v in result.items() if k != "markdown"}
    out_path = ROOT / "samples" / "torg12" / "torg12_example_01.recognized.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out_path)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

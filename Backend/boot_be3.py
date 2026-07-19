"""Minimal process entry for Railway BE3 — no CLI arg parsing pitfalls."""
from __future__ import annotations

import os
import sys
import traceback


def main() -> None:
    raw = (os.environ.get("PORT") or "8000").strip()
    try:
        port = int(raw)
    except ValueError:
        print(f"[boot] invalid PORT={raw!r}, falling back to 8000", flush=True)
        port = 8000
    print(f"[boot] PYTHONPATH={os.environ.get('PYTHONPATH')!r} PORT={port}", flush=True)
    try:
        import uvicorn
        from app.main import app
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print(f"[boot] starting uvicorn app.main:app on 0.0.0.0:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()

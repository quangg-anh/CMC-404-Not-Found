"""Minimal process entry for Railway BE2."""
from __future__ import annotations

import os
import sys
import traceback


def main() -> None:
    port = int(os.environ.get("PORT") or "8002")
    print(f"[boot] BE2 PORT={port}", flush=True)
    try:
        import uvicorn
        from be2_service import app
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print(f"[boot] starting be2_service on 0.0.0.0:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()

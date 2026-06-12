from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def mask_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    netloc = parts.netloc
    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        netloc = f"{user}:***@{host}" if user else f"***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main() -> int:
    from backend.app.core.config import get_settings

    redis_url = os.environ.get("REDIS_URL") or get_settings().redis_url
    report = {
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "redis_url": mask_url(redis_url),
        "status": "unknown",
        "message": "",
    }
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        pong = client.ping()
        report.update({"status": "pass" if pong else "fail", "message": "redis ping ok" if pong else "redis ping returned false"})
    except Exception as exc:
        report.update({"status": "fail", "message": f"{type(exc).__name__}: {exc}"})

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

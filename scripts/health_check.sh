#!/bin/sh
set -eu

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

python - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
paths = ["/health", "/api/db/health", "/api/tasks/health"]
result = {"base_url": base_url, "checks": []}
ok = True
for path in paths:
    url = base_url + path
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.status
            item = {"path": path, "status_code": status, "ok": 200 <= status < 300}
            try:
                item["body"] = json.loads(body)
            except Exception:
                item["body"] = body[:200]
    except Exception as exc:
        item = {"path": path, "status_code": 0, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    ok = ok and bool(item["ok"])
    result["checks"].append(item)
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if ok else 1)
PY

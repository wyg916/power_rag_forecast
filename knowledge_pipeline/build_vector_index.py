from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.vector_index_service import build_vector_index


def main() -> int:
    result = build_vector_index(expected_dim=1024)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("available") else 1


if __name__ == "__main__":
    raise SystemExit(main())

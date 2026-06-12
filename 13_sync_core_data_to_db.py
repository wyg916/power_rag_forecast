from __future__ import annotations

import json

from backend.app.services.core_data_sync import sync_core_facts_and_tariff_assets


def main() -> int:
    result = sync_core_facts_and_tariff_assets(log=print)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

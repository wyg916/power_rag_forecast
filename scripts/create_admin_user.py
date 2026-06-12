from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.auth.password import hash_password
from backend.app.repositories.user_repository import create_user, get_user_by_username


def main() -> int:
    username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com").strip()
    display_name = os.environ.get("ADMIN_DISPLAY_NAME", username).strip()
    if not username:
        print("ADMIN_USERNAME is required")
        return 2
    if not password:
        print("ADMIN_PASSWORD is required; password was not printed or stored.")
        return 2
    existing = get_user_by_username(username)
    if existing:
        print(f"Admin user already exists: username={username}, role={existing.get('role')}")
        return 0
    user = create_user(
        username=username,
        password_hash=hash_password(password),
        email=email,
        display_name=display_name,
        role="admin",
        is_active=True,
        is_superuser=True,
    )
    print(f"Admin user created: username={user.get('username')}, role={user.get('role')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

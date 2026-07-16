from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.auth.password import hash_password
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import reset_db_cache
from backend.app.repositories.user_repository import create_user, get_user_by_username
from backend.app.services.settings_center_service import seed_settings_defaults, test_all_interfaces
from backend.app.core.security import CurrentUser


def seed_users() -> None:
    default_password = os.getenv("SETTINGS_SEED_DEFAULT_PASSWORD", "ChangeMe@2026!")
    users = [
        ("admin", "超级管理员", "admin", "admin@example.local"),
        ("zhangsan", "张三", "analyst", "zhangsan@example.local"),
        ("lisi", "李四", "developer", "lisi@example.local"),
        ("wangwu", "王五", "viewer", "wangwu@example.local"),
        ("zhaoliu", "赵六", "operator", "zhaoliu@example.local"),
    ]
    password_hash = hash_password(default_password)
    for username, display_name, role, email in users:
        if get_user_by_username(username):
            continue
        create_user(
            username=username,
            password_hash=password_hash,
            email=email,
            display_name=display_name,
            role=role,
            is_active=True,
            is_superuser=role == "admin",
        )


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required. Set it before running this seed script.")
    reset_settings_cache()
    reset_db_cache()
    seed_settings_defaults(updated_by="seed_script")
    seed_users()
    user = CurrentUser(user_id="seed_script", username="seed_script", role="admin", permissions=["*"], auth_mode="seed")
    test_all_interfaces(user=user, ip_address="127.0.0.1")
    print("settings center seed completed")


if __name__ == "__main__":
    main()

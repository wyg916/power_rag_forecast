# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path

from database_utils import _split_sql_statements


class MigrationTests(unittest.TestCase):
    def test_migration_sql_is_idempotent(self):
        migration_dir = Path("migrations")
        sql_files = sorted(migration_dir.glob("*.sql"))
        self.assertGreaterEqual(len(sql_files), 4)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in sql_files)
        self.assertIn("CREATE TABLE IF NOT EXISTS model_registry", combined)
        self.assertIn("CREATE TABLE IF NOT EXISTS prediction_tracking", combined)
        self.assertNotIn("DROP TABLE", combined.upper())

    def test_sql_splitter_handles_multiple_statements(self):
        statements = _split_sql_statements("CREATE TABLE IF NOT EXISTS a (id INT);\n-- comment\nCREATE TABLE IF NOT EXISTS b (id INT);")
        self.assertEqual(len(statements), 2)


if __name__ == "__main__":
    unittest.main()

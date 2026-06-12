# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path


class StartupScriptTests(unittest.TestCase):
    def test_bat_files_use_crlf_and_error_pause_guard(self):
        for path in Path(".").glob("*.bat"):
            data = path.read_bytes()
            self.assertIn(b"\r\n", data, path.name)
            if path.name.startswith("run_") or path.name.startswith("create_"):
                text = data.decode("utf-8")
                self.assertIn("NO_PAUSE", text, path.name)

    def test_health_check_entry_exists(self):
        self.assertTrue(Path("run_health_check.bat").exists())
        self.assertTrue(Path("09_health_check.py").exists())


if __name__ == "__main__":
    unittest.main()

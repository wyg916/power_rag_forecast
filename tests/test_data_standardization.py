# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from prediction_engine.features import standardize_datetime_frame


class DataStandardizationTests(unittest.TestCase):
    def test_standardize_datetime_frame_sorts_deduplicates_and_drops_bad_dates(self):
        raw = pd.DataFrame(
            {
                "datetime": ["2026-01-02 01:00", "bad-date", "2026-01-02 00:00", "2026-01-02 00:00"],
                "value": [2, 99, 1, 3],
            }
        )
        result = standardize_datetime_frame(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["datetime"].dt.hour.tolist(), [0, 1])
        self.assertEqual(result["value"].tolist(), [1, 2])


if __name__ == "__main__":
    unittest.main()

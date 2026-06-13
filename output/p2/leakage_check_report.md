# P2 Leakage Check Report

- created_at: 2026-06-13T13:30:15
- acceptable_for_backtest: True
- high_risk_count: 0
- medium_risk_count: 0

## Split Windows

- train: rows=16077, start=2024-06-10 00:00:00, end=2026-04-10 22:00:00
- validation: rows=720, start=2026-04-10 23:00:00, end=2026-05-10 22:00:00
- test: rows=721, start=2026-05-10 23:00:00, end=2026-06-09 23:00:00

## Checks

- time_split_chronological: True
- random_shuffle_detected: False
- target_not_used_as_feature: True
- forecast_results_not_used: True
- feature_time_not_after_target: True

## Issues

- No leakage issues detected.

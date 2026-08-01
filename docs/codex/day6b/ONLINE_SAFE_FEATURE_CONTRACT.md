# Day 6B online-safe feature contract

- legacy_feature_rows: 170
- candidate_feature_count: 52
- feature_version: `features_online_safe_289a51530a13`
- contract: every candidate source cutoff is no later than target minus 24 hours; load/weather use an additional reporting guard.
- runtime note: historical source freshness remains a fail-closed admission requirement.

## Day 6A decision counts

- block: 89
- allow: 66
- retrain_required: 15

## 15 retrain_required dispositions

| feature | strategy | candidate feature | status |
|---|---|---|---|
| price_spread_rt_minus_da_lag_1 | remove | - | excluded |
| actual_load_lag_1 | lagged_replacement | actual_load_lag_25 | replaced |
| actual_load_lag_2 | lagged_replacement | actual_load_lag_25 | replaced |
| actual_load_hist_change_1h | lagged_replacement | actual_load_lag_25 | replaced |
| actual_load_roll_mean_24 | deterministic_online_derivation | actual_load_anchor_mean_24 | replaced |
| actual_load_roll_std_24 | deterministic_online_derivation | actual_load_anchor_std_24 | replaced |
| actual_load_roll_mean_168 | deterministic_online_derivation | actual_load_anchor_mean_168 | replaced |
| actual_load_roll_std_168 | deterministic_online_derivation | actual_load_anchor_std_168 | replaced |
| actual_load_ewm_mean_24 | deterministic_online_derivation | actual_load_anchor_mean_24 | replaced |
| actual_load_ewm_std_24 | deterministic_online_derivation | actual_load_anchor_std_24 | replaced |
| actual_load_ewm_mean_168 | deterministic_online_derivation | actual_load_anchor_mean_168 | replaced |
| actual_load_ewm_std_168 | deterministic_online_derivation | actual_load_anchor_std_168 | replaced |
| hour_bias_mean | remove | - | excluded |
| scenario_mae | remove | - | excluded |
| historical_under_predict_rate | remove | - | excluded |

## 89 block classification

- provider_missing: 56
- data_freshness_issue: 33

The row-level comparison is in `ONLINE_SAFE_FEATURE_CONTRACT.csv`.

# Day 6B online-safe candidate model card

- model_version: `model_day6b_20260801_181807`
- feature_version: `features_online_safe_289a51530a13`
- intended horizon: next 24 hourly day-ahead price targets
- inputs: deterministic calendar plus causally shifted historical facts only
- forbidden inputs: future actual load, realized real-time price/spread, zero placeholders, historical copy/date shift fallbacks
- status: `candidate / NOT PASS / not registered / not active`
- limitation: current source freshness and restricted PostgreSQL lineage were not proven in this run

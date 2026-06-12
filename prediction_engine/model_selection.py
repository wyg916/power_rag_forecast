from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .legacy_engine import load_engine_module


def get_model_candidates() -> List[Dict]:
    return load_engine_module().get_model_candidates()


def get_peak_candidates() -> List[Dict]:
    return load_engine_module().get_peak_specialist_candidates()


def get_peak_specialist_candidates() -> List[Dict]:
    return get_peak_candidates()


def get_peak_classifier_candidates() -> List[Dict]:
    return load_engine_module().get_peak_classifier_candidates()


def blend_predictions(
    base_pred,
    peak_pred,
    risk_prob,
    peak_hour_flag,
    alpha: float,
    peak_floor: float,
    load_high_flag=None,
    error_high_flag=None,
    spike_threshold: float = 0.5,
):
    return load_engine_module().blend_predictions(
        base_pred,
        peak_pred,
        risk_prob,
        peak_hour_flag,
        alpha,
        peak_floor,
        load_high_flag=load_high_flag,
        error_high_flag=error_high_flag,
        spike_threshold=spike_threshold,
    )


def search_best_blend(
    base_pred_val,
    peak_pred_val,
    risk_prob_val,
    val_df,
    y_val,
    spike_threshold: float = 0.5,
) -> Tuple[float, float, pd.DataFrame]:
    return load_engine_module().search_best_blend(
        base_pred_val,
        peak_pred_val,
        risk_prob_val,
        val_df,
        y_val,
        spike_threshold=spike_threshold,
    )

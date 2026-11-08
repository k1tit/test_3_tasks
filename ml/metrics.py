from __future__ import annotations

import math

import numpy as np


def regression_metrics(actual, predicted) -> dict[str, float]:
    y_true = np.asarray(actual, dtype=float)
    y_pred = np.asarray(predicted, dtype=float)
    if y_true.size == 0:
        raise ValueError("metrics need at least one row")
    residual = y_true - y_pred
    ss_res = float(np.sum(residual ** 2))
    centered = y_true - float(np.mean(y_true))
    ss_tot = float(np.sum(centered ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else math.nan
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    mape = float(np.mean(np.abs(residual / y_true)) * 100.0)
    return {"r2": r2, "mape_pct": mape, "rmse_rub": rmse, "mae_rub": mae}

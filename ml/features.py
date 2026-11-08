from __future__ import annotations

import math

SEED = 20261026
CHAMPION = "CatBoostRegressor"
PERIOD_MONTH = 12.0
PERIOD_DOW = 7.0
PERIOD_DOY = 365.25
UNKNOWN = "Не указан"

CATEGORICAL_FEATURES = (
    "body_group",
    "weight_category",
    "volume_category",
    "origin_region",
    "destination_region",
)

NUMERIC_FEATURES = (
    "distance",
    "total_weight",
    "total_volume",
    "origin_latitude",
    "origin_longitude",
    "destination_latitude",
    "destination_longitude",
    "year",
    "month",
    "day_of_week",
    "day_of_year",
    "month_sin",
    "month_cos",
    "dow_sin",
    "dow_cos",
    "doy_sin",
    "doy_cos",
)

FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES

FORBIDDEN_COLUMNS = (
    "price_rub",
    "price_src",
    "price_km",
    "price_with_vat",
    "outlier_mark",
    "price_group_id",
    "avg_price",
    "min_km_price",
    "max_km_price",
    "fx_rate",
)


def cycle(value: float, period: float) -> tuple[float, float]:
    angle = 2.0 * math.pi * value / period
    return math.sin(angle), math.cos(angle)

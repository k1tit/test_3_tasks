from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from catboost import CatBoostRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeRegressor

from etl.log import log_event
from ml.features import (
    CATEGORICAL_FEATURES,
    CHAMPION,
    FEATURE_COLUMNS,
    FORBIDDEN_COLUMNS,
    NUMERIC_FEATURES,
    PERIOD_DOW,
    PERIOD_DOY,
    PERIOD_MONTH,
    SEED,
    UNKNOWN,
    cycle,
)
from ml.metrics import regression_metrics
from ml.split import assign_split, split_bounds

DATASET_SQL = Path(__file__).resolve().parent / "sql" / "dataset.sql"


@dataclass(frozen=True)
class TrainSummary:
    train_rows: int
    test_rows: int
    future_rows: int
    champion: str
    r2: float
    mape_pct: float
    rmse_rub: float
    mae_rub: float


def _load_frame(conn, train_start: date) -> pd.DataFrame:
    cursor = conn.execute(DATASET_SQL.read_text(encoding="utf-8"), {"train_start": train_start})
    columns = [column.name for column in cursor.description]
    frame = pd.DataFrame(cursor.fetchall(), columns=columns)
    leaked = set(FEATURE_COLUMNS) & set(FORBIDDEN_COLUMNS)
    if leaked:
        raise RuntimeError(f"feature list contains target leakage: {sorted(leaked)}")
    return frame


def _with_calendar(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    dates = pd.to_datetime(prepared["loading_date"])
    prepared["year"] = dates.dt.year.astype(int)
    prepared["month"] = dates.dt.month.astype(int)
    prepared["day_of_week"] = dates.dt.dayofweek.astype(int)
    prepared["day_of_year"] = dates.dt.dayofyear.astype(int)
    prepared["loading_date"] = dates.dt.date
    for source, period, prefix in (
        ("month", PERIOD_MONTH, "month"),
        ("day_of_week", PERIOD_DOW, "dow"),
        ("day_of_year", PERIOD_DOY, "doy"),
    ):
        angles = [cycle(float(value), period) for value in prepared[source].tolist()]
        prepared[f"{prefix}_sin"] = [item[0] for item in angles]
        prepared[f"{prefix}_cos"] = [item[1] for item in angles]
    for column in CATEGORICAL_FEATURES:
        prepared[column] = prepared[column].fillna(UNKNOWN).astype(str).replace({"": UNKNOWN})
    return prepared


def _populations(frame: pd.DataFrame, as_of: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    labels = frame["loading_date"].map(lambda value: assign_split(value, as_of))
    evaluable = (
        frame["is_fact"].astype(bool)
        & ~frame["complex"].astype(bool)
        & ~frame["outlier_mark"].astype(bool)
        & (frame["distance"] > 0)
        & (frame["price_rub"] > 0)
    )
    train = frame.loc[evaluable & (labels == "train")].copy()
    test = frame.loc[evaluable & (labels == "test")].copy()
    future = frame.loc[labels == "future"].copy()
    return train, test, future


def _baseline(name: str, estimator) -> Pipeline:
    categories = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    numbers = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    prepared = ColumnTransformer(
        transformers=[
            ("categories", categories, list(CATEGORICAL_FEATURES)),
            ("numbers", numbers, list(NUMERIC_FEATURES)),
        ]
    )
    return Pipeline(steps=[("prepare", prepared), (name, estimator)])


def _fit_baselines(train: pd.DataFrame, test: pd.DataFrame) -> list[tuple[str, dict[str, float]]]:
    features = list(FEATURE_COLUMNS)
    target = train["price_rub"].to_numpy(dtype=float)
    fitted = []
    models = (
        (
            "DecisionTreeRegressor",
            DecisionTreeRegressor(max_depth=12, min_samples_leaf=50, random_state=SEED),
        ),
        ("Ridge", Ridge(alpha=1.0)),
    )
    for name, estimator in models:
        pipeline = _baseline(name, estimator)
        pipeline.fit(train[features], target)
        predicted = pipeline.predict(test[features])
        fitted.append((name, regression_metrics(test["price_rub"], predicted)))
    return fitted


def _champion_model(train: pd.DataFrame) -> CatBoostRegressor:
    model = CatBoostRegressor(
        iterations=400,
        depth=8,
        learning_rate=0.08,
        loss_function="RMSE",
        random_seed=SEED,
        verbose=False,
        allow_writing_files=False,
    )
    model.fit(
        train[list(FEATURE_COLUMNS)],
        train["price_rub"].to_numpy(dtype=float),
        cat_features=list(CATEGORICAL_FEATURES),
    )
    return model


def _prediction_rows(score: pd.DataFrame, as_of: date) -> list[tuple]:
    rows = []
    for item in score.itertuples(index=False):
        forecast = float(item.predicted)
        if not math.isfinite(forecast):
            raise RuntimeError(f"model returned a non-finite forecast for price_id={item.price_id}")
        actual = None if item.loading_date > as_of else float(item.price_rub)
        if actual is None:
            absolute = None
            ape = None
        else:
            absolute = abs(actual - forecast)
            ape = absolute / actual * 100.0
        rows.append(
            (
                int(item.price_id),
                item.loading_date,
                int(item.loading_city_gcid),
                int(item.unloading_city_gcid),
                str(item.body_group),
                actual,
                forecast,
                absolute,
                ape,
                CHAMPION,
            )
        )
    return rows


def _replace_predictions(conn, rows: list[tuple]) -> None:
    conn.execute("DELETE FROM mart.ml_price_predictions")
    if not rows:
        return
    with conn.cursor() as cursor:
        with cursor.copy(
            """
            COPY mart.ml_price_predictions (
                price_id, loading_date, loading_city_gcid, unloading_city_gcid, body_group,
                actual_price_rub, predicted_price_rub, abs_error_rub, ape_pct, model_name
            ) FROM STDIN
            """
        ) as copy:
            for row in rows:
                copy.write_row(row)


def _replace_metrics(conn, rows: list[tuple]) -> None:
    conn.execute("DELETE FROM mart.ml_model_metrics")
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO mart.ml_model_metrics (
                model_name, train_rows, test_rows, r2, mape_pct, rmse_rub, mae_rub, future_rows
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )


def _ensure_predictions(conn, as_of: date, test_rows: int, future_rows: int) -> None:
    broken_future = conn.execute(
        """
        SELECT count(*)
        FROM mart.ml_price_predictions
        WHERE loading_date > %s
          AND (
                actual_price_rub IS NOT NULL
                OR abs_error_rub IS NOT NULL
                OR ape_pct IS NOT NULL
          )
        """,
        (as_of,),
    ).fetchone()[0]
    missing_actual = conn.execute(
        """
        SELECT count(*)
        FROM mart.ml_price_predictions
        WHERE loading_date <= %s AND actual_price_rub IS NULL
        """,
        (as_of,),
    ).fetchone()[0]
    stored = conn.execute("SELECT count(*) FROM mart.ml_price_predictions").fetchone()[0]
    if broken_future or missing_actual or stored != test_rows + future_rows:
        raise RuntimeError(
            "prediction invariant failed: "
            f"future_with_actual={broken_future} test_without_actual={missing_actual} "
            f"stored={stored} expected={test_rows + future_rows}"
        )


def _log_metrics(name: str, metrics: dict[str, float]) -> None:
    log_event(
        "ml_metrics",
        model=name,
        r2=round(metrics["r2"], 4),
        mape_pct=round(metrics["mape_pct"], 2),
        rmse_rub=round(metrics["rmse_rub"], 2),
        mae_rub=round(metrics["mae_rub"], 2),
    )


def train_and_score(conn, as_of: date) -> TrainSummary:
    train_start, test_start = split_bounds(as_of)
    frame = _with_calendar(_load_frame(conn, train_start))
    train, test, future = _populations(frame, as_of)
    if train.empty or test.empty:
        raise RuntimeError(
            f"empty ml split for as_of={as_of.isoformat()}: train={len(train)} test={len(test)}"
        )
    log_event(
        "ml_split",
        as_of=as_of.isoformat(),
        train_start=train_start.isoformat(),
        test_start=test_start.isoformat(),
        train_rows=len(train),
        test_rows=len(test),
        future_rows=len(future),
    )
    metric_rows = []
    for name, metrics in _fit_baselines(train, test):
        metric_rows.append(
            (
                name,
                len(train),
                len(test),
                metrics["r2"],
                metrics["mape_pct"],
                metrics["rmse_rub"],
                metrics["mae_rub"],
                0,
            )
        )
        _log_metrics(name, metrics)
    features = list(FEATURE_COLUMNS)
    model = _champion_model(train)
    test = test.copy()
    test["predicted"] = model.predict(test[features])
    champion = regression_metrics(test["price_rub"], test["predicted"])
    if future.empty:
        score = test
    else:
        future = future.copy()
        future["predicted"] = model.predict(future[features])
        score = pd.concat([test, future], ignore_index=True)
    if not score["price_id"].is_unique:
        raise RuntimeError("score set contains duplicate price_id")
    score = score.sort_values("price_id")
    rows = _prediction_rows(score, as_of)
    metric_rows.append(
        (
            CHAMPION,
            len(train),
            len(test),
            champion["r2"],
            champion["mape_pct"],
            champion["rmse_rub"],
            champion["mae_rub"],
            len(future),
        )
    )
    _replace_predictions(conn, rows)
    _replace_metrics(conn, metric_rows)
    _ensure_predictions(conn, as_of, len(test), len(future))
    _log_metrics(CHAMPION, champion)
    log_event(
        "ml_scored",
        model=CHAMPION,
        test_rows=len(test),
        future_rows=len(future),
        stored_rows=len(rows),
    )
    return TrainSummary(
        train_rows=len(train),
        test_rows=len(test),
        future_rows=len(future),
        champion=CHAMPION,
        r2=champion["r2"],
        mape_pct=champion["mape_pct"],
        rmse_rub=champion["rmse_rub"],
        mae_rub=champion["mae_rub"],
    )

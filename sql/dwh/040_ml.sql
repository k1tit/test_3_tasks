CREATE TABLE IF NOT EXISTS mart.ml_price_predictions (
    price_id bigint PRIMARY KEY,
    loading_date date NOT NULL,
    loading_city_gcid integer NOT NULL,
    unloading_city_gcid integer NOT NULL,
    body_group varchar(32) NOT NULL,
    actual_price_rub double precision,
    predicted_price_rub double precision NOT NULL,
    abs_error_rub double precision,
    ape_pct double precision,
    model_name varchar(64) NOT NULL,
    scored_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ml_price_predictions_loading_date_idx
    ON mart.ml_price_predictions (loading_date);

CREATE TABLE IF NOT EXISTS mart.ml_model_metrics (
    model_name varchar(64) PRIMARY KEY,
    train_rows integer NOT NULL,
    test_rows integer NOT NULL,
    r2 double precision,
    mape_pct double precision,
    rmse_rub double precision,
    mae_rub double precision,
    future_rows integer NOT NULL,
    trained_at timestamptz NOT NULL DEFAULT now()
);

SELECT model_name, train_rows, test_rows, future_rows,
       round(r2::numeric, 4) AS r2,
       round(mape_pct::numeric, 2) AS mape_pct,
       round(rmse_rub::numeric, 2) AS rmse_rub,
       round(mae_rub::numeric, 2) AS mae_rub
FROM mart.ml_model_metrics
ORDER BY r2 DESC;

SELECT
    count(*) AS scored_rows,
    count(*) FILTER (WHERE actual_price_rub IS NULL) AS future_rows,
    count(*) FILTER (WHERE loading_date > DATE '2026-10-26' AND actual_price_rub IS NOT NULL) AS future_with_actual
FROM mart.ml_price_predictions;

SELECT
    price_id,
    loading_date,
    body_group,
    round(actual_price_rub::numeric, 2) AS actual_price_rub,
    round(predicted_price_rub::numeric, 2) AS predicted_price_rub,
    round(abs_error_rub::numeric, 2) AS abs_error_rub,
    round(ape_pct::numeric, 2) AS ape_pct
FROM mart.ml_price_predictions
WHERE actual_price_rub IS NOT NULL
ORDER BY ape_pct DESC NULLS LAST
LIMIT 10;

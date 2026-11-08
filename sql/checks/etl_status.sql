SELECT
    run_id,
    status,
    start_date,
    end_date,
    source_rows,
    core_rows,
    quarantine_rows,
    outlier_rows,
    started_at,
    finished_at,
    error
FROM etl.run_log
ORDER BY run_id DESC
LIMIT 10;

SELECT code, count(*) AS rows
FROM dq.quarantine_prices q
CROSS JOIN LATERAL unnest(q.reason_codes) AS code
GROUP BY code
ORDER BY rows DESC, code;

SELECT
    count(*) AS core_rows,
    count(*) FILTER (WHERE outlier_mark) AS outlier_rows,
    count(*) FILTER (WHERE loading_city_gcid = unloading_city_gcid) AS same_city_rows,
    count(*) FILTER (WHERE NOT is_fact) AS non_fact_rows,
    count(*) FILTER (WHERE complex) AS complex_rows,
    count(*) FILTER (WHERE body_type IS NULL) AS null_body_rows,
    round(sum(price_rub)::numeric, 2) AS price_rub_sum
FROM core.prices;

SELECT
    reliability_level,
    count(*) AS cells,
    sum(trips_count) AS trips
FROM mart.route_card
GROUP BY reliability_level
ORDER BY reliability_level;

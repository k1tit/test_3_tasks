INSERT INTO dq.quarantine_prices (
    price_id,
    loading_date,
    reason_codes,
    price,
    currency_code,
    distance,
    total_weight,
    total_volume,
    loading_city_gcid,
    unloading_city_gcid,
    nearest_rate_date,
    price_type,
    is_fact
)
SELECT
    price_id,
    loading_date,
    reason_codes,
    price_src,
    currency_code,
    distance,
    total_weight,
    total_volume,
    loading_city_gcid,
    unloading_city_gcid,
    nearest_rate_date,
    price_type,
    is_fact
FROM etl_classified
WHERE cardinality(reason_codes) > 0;

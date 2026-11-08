DROP TABLE IF EXISTS etl_classified;

CREATE TEMP TABLE etl_classified AS
WITH city_ids AS (
    SELECT DISTINCT gc_id
    FROM public.cities
)
SELECT
    p.id AS price_id,
    p.created_at,
    p.loading_date,
    p.end_loading_date,
    p.loading_city_gcid,
    p.unloading_city_gcid,
    p.distance,
    p.total_weight,
    p.total_volume,
    COALESCE(NULLIF(btrim(p.weight_category), ''), core.weight_category(p.total_weight)) AS weight_category,
    COALESCE(NULLIF(btrim(p.volume_category), ''), core.volume_category(p.total_volume)) AS volume_category,
    p.body_type,
    p.price AS price_src,
    btrim(p.currency_code) AS currency_code,
    CASE
        WHEN btrim(p.currency_code) = '643' THEN COALESCE(er.fx_rate, 1.0)
        ELSE er.fx_rate
    END AS fx_rate,
    CASE
        WHEN er.fx_rate IS NOT NULL THEN p.nearest_rate_date
        ELSE NULL
    END AS fx_rate_date,
    p.price_type,
    p.is_fact,
    p.complex,
    p.organization_id,
    p.subscriber_id,
    p.outlier_mark,
    p.source,
    p.nearest_rate_date,
    dq.price_reason_codes(
        p.price,
        btrim(p.currency_code),
        p.distance,
        p.total_weight,
        p.total_volume,
        lc.gc_id IS NOT NULL,
        uc.gc_id IS NOT NULL,
        CASE
            WHEN btrim(p.currency_code) = '643' THEN true
            WHEN btrim(p.currency_code) IN ('840', '978') THEN er.fx_rate IS NOT NULL
            ELSE false
        END
    ) AS reason_codes
FROM public.prices p
CROSS JOIN etl_bounds b
LEFT JOIN city_ids lc ON lc.gc_id = p.loading_city_gcid
LEFT JOIN city_ids uc ON uc.gc_id = p.unloading_city_gcid
LEFT JOIN LATERAL (
    SELECT er.value AS fx_rate
    FROM public.exchange_rates er
    WHERE er.num_code = btrim(p.currency_code)
      AND er.setting_date = p.nearest_rate_date
    ORDER BY er.id
    LIMIT 1
) er ON true
WHERE (b.start_date IS NULL OR p.loading_date >= b.start_date)
  AND (b.end_date IS NULL OR p.loading_date <= b.end_date);

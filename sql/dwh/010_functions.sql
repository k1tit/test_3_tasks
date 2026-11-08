CREATE OR REPLACE FUNCTION core.weight_category(total_weight double precision)
RETURNS varchar
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN round(total_weight::numeric, 1) >= 30 THEN 'G20T'
        WHEN round(total_weight::numeric, 1) >= 10 THEN 'FTL'
        WHEN round(total_weight::numeric, 1) >= 5 THEN '10T'
        WHEN round(total_weight::numeric, 1) >= 2.5 THEN '5T'
        WHEN round(total_weight::numeric, 1) >= 0.5 THEN 'L5T'
        ELSE 'OTH'
    END;
$$;

CREATE OR REPLACE FUNCTION core.volume_category(total_volume double precision)
RETURNS varchar
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN total_volume > 0 AND total_volume <= 120 THEN 'FTL'
        ELSE 'OTH'
    END;
$$;

CREATE OR REPLACE FUNCTION core.body_group(body_type_id integer)
RETURNS varchar
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN body_type_id IN (56, 57, 58, 59, 60, 61) THEN 'Тент'
        WHEN body_type_id IN (4, 46, 47, 48) THEN 'Рефрижератор'
        WHEN body_type_id = 2 THEN 'Изотерм'
        WHEN body_type_id IN (1, 15) THEN 'Борт'
        WHEN body_type_id IS NULL THEN 'Не указан'
        ELSE 'Прочие'
    END;
$$;

CREATE OR REPLACE FUNCTION dq.price_reason_codes(
    price double precision,
    currency_code varchar,
    distance double precision,
    total_weight double precision,
    total_volume double precision,
    loading_city_known boolean,
    unloading_city_known boolean,
    fx_rate_found boolean
)
RETURNS text[]
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(array_agg(s.code ORDER BY s.ord), ARRAY[]::text[])
    FROM (
        SELECT 1 AS ord, 'UNKNOWN_LOADING_CITY'::text AS code
        WHERE NOT loading_city_known
        UNION ALL
        SELECT 2, 'UNKNOWN_UNLOADING_CITY'
        WHERE NOT unloading_city_known
        UNION ALL
        SELECT 3, 'NON_POSITIVE_DISTANCE'
        WHERE distance IS NULL OR distance <= 0 OR distance <> distance
        UNION ALL
        SELECT 4, 'NEGATIVE_WEIGHT'
        WHERE total_weight IS NULL OR total_weight < 0 OR total_weight <> total_weight
        UNION ALL
        SELECT 5, 'NEGATIVE_VOLUME'
        WHERE total_volume IS NULL OR total_volume < 0 OR total_volume <> total_volume
        UNION ALL
        SELECT 6, 'NON_POSITIVE_PRICE'
        WHERE price IS NULL OR price <= 0 OR price <> price
        UNION ALL
        SELECT 7, 'RUB_PRICE_BELOW_MIN'
        WHERE currency_code = '643' AND price <= 1000 AND price = price
        UNION ALL
        SELECT 8, 'UNKNOWN_CURRENCY'
        WHERE currency_code IS NULL OR currency_code NOT IN ('643', '840', '978')
        UNION ALL
        SELECT 9, 'MISSING_FX_RATE'
        WHERE currency_code IN ('840', '978') AND NOT fx_rate_found
    ) s;
$$;

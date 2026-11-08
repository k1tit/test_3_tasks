DELETE FROM mart.route_card;

INSERT INTO mart.route_card (
    month_date,
    loading_city_gcid,
    unloading_city_gcid,
    loading_city_name,
    unloading_city_name,
    loading_region_name,
    unloading_region_name,
    body_group,
    weight_category,
    p25_trip,
    median_trip,
    p75_trip,
    avg_trip,
    p25_km,
    median_km,
    p75_km,
    trips_count,
    carriers_count,
    cv_rate,
    mom_pct,
    yoy_pct,
    reliability_level,
    last_price_date,
    as_of_date
)
WITH as_of AS (
    SELECT as_of_date
    FROM etl_as_of
),
eligible AS (
    SELECT
        p.price_id,
        p.loading_city_gcid,
        p.unloading_city_gcid,
        lc.city_name AS loading_city_name,
        uc.city_name AS unloading_city_name,
        lc.region_name AS loading_region_name,
        uc.region_name AS unloading_region_name,
        p.body_type,
        p.weight_category,
        p.price_rub,
        p.price_rub / p.distance AS price_km,
        p.organization_id,
        p.price_type
    FROM core.prices p
    JOIN core.cities lc ON lc.gc_id = p.loading_city_gcid
    JOIN core.cities uc ON uc.gc_id = p.unloading_city_gcid
    WHERE p.is_fact
      AND p.price_type IN (1, 2, 3, 4, 5, 9)
      AND NOT p.complex
      AND NOT p.outlier_mark
      AND p.price_rub > 0
      AND p.distance > 0
),
grouped AS (
    SELECT pbt.price_id, core.body_group(pbt.body_type_id) AS body_group
    FROM public.price_body_types pbt
    JOIN eligible e ON e.price_id = pbt.price_id
    UNION
    SELECT e.price_id, core.body_group(e.body_type)
    FROM eligible e
    WHERE NOT EXISTS (
        SELECT 1
        FROM public.price_body_types pbt
        WHERE pbt.price_id = e.price_id
    )
),
deal_month AS (
    SELECT DISTINCT ON (g.price_id, g.body_group, date_trunc('month', pd.price_date))
        date_trunc('month', pd.price_date)::date AS month_date,
        pd.price_date AS last_price_date,
        e.price_id,
        e.loading_city_gcid,
        e.unloading_city_gcid,
        e.loading_city_name,
        e.unloading_city_name,
        e.loading_region_name,
        e.unloading_region_name,
        g.body_group,
        e.weight_category,
        e.price_rub,
        e.price_km,
        e.organization_id,
        e.price_type
    FROM grouped g
    JOIN eligible e ON e.price_id = g.price_id
    JOIN public.price_dates pd ON pd.price_id = g.price_id
    CROSS JOIN as_of a
    WHERE pd.price_date <= a.as_of_date
    ORDER BY g.price_id, g.body_group, date_trunc('month', pd.price_date), pd.price_date DESC
),
cells AS (
    SELECT
        month_date,
        loading_city_gcid,
        unloading_city_gcid,
        min(loading_city_name) AS loading_city_name,
        min(unloading_city_name) AS unloading_city_name,
        min(loading_region_name) AS loading_region_name,
        min(unloading_region_name) AS unloading_region_name,
        body_group,
        weight_category,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY price_rub) AS p25_trip,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY price_rub) AS median_trip,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY price_rub) AS p75_trip,
        avg(price_rub) AS avg_trip,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY price_km) AS p25_km,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY price_km) AS median_km,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY price_km) AS p75_km,
        count(*)::integer AS trips_count,
        count(DISTINCT CASE WHEN price_type IN (3, 9) THEN organization_id END)::integer AS carriers_count,
        CASE
            WHEN count(*) < 2 OR avg(price_rub) = 0 THEN NULL
            ELSE stddev_samp(price_rub) / avg(price_rub)
        END AS cv_rate,
        max(last_price_date) AS last_price_date
    FROM deal_month
    GROUP BY month_date, loading_city_gcid, unloading_city_gcid, body_group, weight_category
)
SELECT
    c.month_date,
    c.loading_city_gcid,
    c.unloading_city_gcid,
    c.loading_city_name,
    c.unloading_city_name,
    c.loading_region_name,
    c.unloading_region_name,
    c.body_group,
    c.weight_category,
    c.p25_trip,
    c.median_trip,
    c.p75_trip,
    c.avg_trip,
    c.p25_km,
    c.median_km,
    c.p75_km,
    c.trips_count,
    c.carriers_count,
    c.cv_rate,
    CASE
        WHEN mom.median_trip IS NULL OR mom.median_trip = 0 THEN NULL
        ELSE (c.median_trip - mom.median_trip) / mom.median_trip * 100
    END AS mom_pct,
    CASE
        WHEN yoy.median_trip IS NULL OR yoy.median_trip = 0 THEN NULL
        ELSE (c.median_trip - yoy.median_trip) / yoy.median_trip * 100
    END AS yoy_pct,
    CASE
        WHEN c.trips_count >= 30
         AND c.carriers_count >= 5
         AND (a.as_of_date - c.last_price_date) <= 30
        THEN 'HIGH'
        WHEN c.trips_count >= 10 THEN 'MEDIUM'
        ELSE 'LOW_DATA'
    END AS reliability_level,
    c.last_price_date,
    a.as_of_date
FROM cells c
CROSS JOIN as_of a
LEFT JOIN cells mom
    ON mom.loading_city_gcid = c.loading_city_gcid
   AND mom.unloading_city_gcid = c.unloading_city_gcid
   AND mom.body_group = c.body_group
   AND mom.weight_category = c.weight_category
   AND mom.month_date = (c.month_date - INTERVAL '1 month')::date
LEFT JOIN cells yoy
    ON yoy.loading_city_gcid = c.loading_city_gcid
   AND yoy.unloading_city_gcid = c.unloading_city_gcid
   AND yoy.body_group = c.body_group
   AND yoy.weight_category = c.weight_category
   AND yoy.month_date = (c.month_date - INTERVAL '1 year')::date;

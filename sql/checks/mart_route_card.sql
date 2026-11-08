SELECT
    month_date,
    loading_city_name,
    unloading_city_name,
    body_group,
    weight_category,
    round(p25_trip::numeric, 2) AS p25_trip,
    round(median_trip::numeric, 2) AS median_trip,
    round(p75_trip::numeric, 2) AS p75_trip,
    round(avg_trip::numeric, 2) AS avg_trip,
    round(median_km::numeric, 2) AS median_km,
    trips_count,
    carriers_count,
    round(cv_rate::numeric, 4) AS cv_rate,
    round(mom_pct::numeric, 2) AS mom_pct,
    round(yoy_pct::numeric, 2) AS yoy_pct,
    reliability_level
FROM mart.route_card
ORDER BY trips_count DESC, month_date DESC
LIMIT 20;

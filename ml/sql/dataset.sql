SELECT
    p.price_id,
    p.loading_date,
    p.loading_city_gcid,
    p.unloading_city_gcid,
    p.distance,
    p.total_weight,
    p.total_volume,
    p.weight_category,
    p.volume_category,
    core.body_group(p.body_type) AS body_group,
    COALESCE(NULLIF(btrim(lc.region_name), ''), 'Не указан') AS origin_region,
    COALESCE(NULLIF(btrim(uc.region_name), ''), 'Не указан') AS destination_region,
    lc.latitude AS origin_latitude,
    lc.longitude AS origin_longitude,
    uc.latitude AS destination_latitude,
    uc.longitude AS destination_longitude,
    p.price_rub,
    p.is_fact,
    p.complex,
    p.outlier_mark
FROM core.prices p
JOIN core.cities lc ON lc.gc_id = p.loading_city_gcid
JOIN core.cities uc ON uc.gc_id = p.unloading_city_gcid
WHERE p.loading_date >= %(train_start)s;

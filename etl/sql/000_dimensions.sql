DELETE FROM core.cities c
WHERE NOT EXISTS (
    SELECT 1
    FROM public.cities s
    WHERE s.gc_id = c.gc_id
);

INSERT INTO core.cities (
    city_id,
    gc_id,
    name,
    full_name_local,
    city_name,
    region_name,
    latitude,
    longitude
)
SELECT DISTINCT ON (s.gc_id)
    s.id,
    s.gc_id,
    s.name,
    s.full_name_local,
    btrim(split_part(s.full_name_local, ',', 1)),
    NULLIF(btrim(split_part(s.full_name_local, ',', 2)), ''),
    s.latitude,
    s.longitude
FROM public.cities s
ORDER BY s.gc_id, s.id
ON CONFLICT (gc_id) DO UPDATE SET
    city_id = EXCLUDED.city_id,
    name = EXCLUDED.name,
    full_name_local = EXCLUDED.full_name_local,
    city_name = EXCLUDED.city_name,
    region_name = EXCLUDED.region_name,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude;

DELETE FROM core.body_types b
WHERE NOT EXISTS (
    SELECT 1
    FROM public.body_types s
    WHERE s.id = b.body_type_id
);

INSERT INTO core.body_types (
    body_type_id,
    name,
    id_from_1c,
    std_id,
    body_group
)
SELECT
    s.id,
    s.name,
    s."id_from_1C",
    CASE
        WHEN s.id IN (56, 57, 58, 59, 60, 61) THEN 56
        WHEN s.id IN (4, 46, 47, 48) THEN 4
        WHEN s.id = 2 THEN 2
        WHEN s.id IN (1, 15) THEN 15
        ELSE COALESCE(s.std_id, s.id::integer)
    END,
    core.body_group(s.id::integer)
FROM public.body_types s
ON CONFLICT (body_type_id) DO UPDATE SET
    name = EXCLUDED.name,
    id_from_1c = EXCLUDED.id_from_1c,
    std_id = EXCLUDED.std_id,
    body_group = EXCLUDED.body_group;

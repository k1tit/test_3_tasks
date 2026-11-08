CREATE TABLE IF NOT EXISTS mart.route_card (
    month_date date NOT NULL,
    loading_city_gcid integer NOT NULL,
    unloading_city_gcid integer NOT NULL,
    loading_city_name varchar(255) NOT NULL,
    unloading_city_name varchar(255) NOT NULL,
    loading_region_name varchar(255),
    unloading_region_name varchar(255),
    body_group varchar(32) NOT NULL,
    weight_category varchar(4) NOT NULL,
    p25_trip double precision NOT NULL,
    median_trip double precision NOT NULL,
    p75_trip double precision NOT NULL,
    avg_trip double precision NOT NULL,
    p25_km double precision NOT NULL,
    median_km double precision NOT NULL,
    p75_km double precision NOT NULL,
    trips_count integer NOT NULL,
    carriers_count integer NOT NULL,
    cv_rate double precision,
    mom_pct double precision,
    yoy_pct double precision,
    reliability_level varchar(16) NOT NULL,
    last_price_date date NOT NULL,
    as_of_date date NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (month_date, loading_city_gcid, unloading_city_gcid, body_group, weight_category),
    CONSTRAINT route_card_month_start CHECK (month_date = date_trunc('month', month_date)::date),
    CONSTRAINT route_card_trips_positive CHECK (trips_count > 0),
    CONSTRAINT route_card_carriers_bounded CHECK (carriers_count >= 0 AND carriers_count <= trips_count),
    CONSTRAINT route_card_reliability CHECK (reliability_level IN ('HIGH', 'MEDIUM', 'LOW_DATA'))
);

CREATE INDEX IF NOT EXISTS route_card_route_idx
    ON mart.route_card (loading_city_gcid, unloading_city_gcid, body_group, weight_category, month_date);

ALTER TABLE etl.run_log ADD COLUMN IF NOT EXISTS mart_rows integer;

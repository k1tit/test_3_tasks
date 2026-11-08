CREATE TABLE IF NOT EXISTS core.cities (
    city_id bigint PRIMARY KEY,
    gc_id integer NOT NULL UNIQUE,
    name varchar(255) NOT NULL,
    full_name_local varchar(255) NOT NULL,
    city_name varchar(255) NOT NULL,
    region_name varchar(255),
    latitude double precision,
    longitude double precision
);

CREATE TABLE IF NOT EXISTS core.body_types (
    body_type_id bigint PRIMARY KEY,
    name varchar(255) NOT NULL,
    id_from_1c integer NOT NULL,
    std_id integer,
    body_group varchar(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.prices (
    price_id bigint PRIMARY KEY,
    created_at timestamp(0),
    loading_date date NOT NULL,
    end_loading_date date,
    loading_city_gcid integer NOT NULL,
    unloading_city_gcid integer NOT NULL,
    distance double precision NOT NULL,
    total_weight double precision NOT NULL,
    total_volume double precision NOT NULL,
    weight_category varchar(4) NOT NULL,
    volume_category varchar(4) NOT NULL,
    body_type integer,
    price_src double precision NOT NULL,
    currency_code varchar(3) NOT NULL,
    fx_rate double precision NOT NULL,
    fx_rate_date date,
    price_rub double precision NOT NULL,
    price_type smallint NOT NULL,
    is_fact boolean NOT NULL,
    complex boolean NOT NULL,
    organization_id integer,
    subscriber_id integer,
    outlier_mark boolean NOT NULL,
    source varchar(255),
    loaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT core_prices_distance_positive CHECK (distance > 0),
    CONSTRAINT core_prices_weight_non_negative CHECK (total_weight >= 0),
    CONSTRAINT core_prices_volume_non_negative CHECK (total_volume >= 0),
    CONSTRAINT core_prices_price_src_positive CHECK (price_src > 0),
    CONSTRAINT core_prices_price_rub_positive CHECK (price_rub > 0),
    CONSTRAINT core_prices_fx_positive CHECK (fx_rate > 0),
    CONSTRAINT core_prices_currency CHECK (currency_code IN ('643', '840', '978'))
);

CREATE INDEX IF NOT EXISTS core_prices_loading_date_idx
    ON core.prices (loading_date);

CREATE INDEX IF NOT EXISTS core_prices_route_idx
    ON core.prices (loading_city_gcid, unloading_city_gcid, weight_category, body_type);

CREATE TABLE IF NOT EXISTS dq.quarantine_prices (
    price_id bigint PRIMARY KEY,
    loading_date date NOT NULL,
    reason_codes text[] NOT NULL,
    price double precision,
    currency_code varchar(3),
    distance double precision,
    total_weight double precision,
    total_volume double precision,
    loading_city_gcid integer,
    unloading_city_gcid integer,
    nearest_rate_date date,
    price_type smallint,
    is_fact boolean,
    quarantined_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT quarantine_has_reason CHECK (cardinality(reason_codes) > 0)
);

CREATE INDEX IF NOT EXISTS quarantine_prices_loading_date_idx
    ON dq.quarantine_prices (loading_date);

CREATE OR REPLACE VIEW public.dq_quarantine_prices AS
SELECT *
FROM dq.quarantine_prices;

CREATE TABLE IF NOT EXISTS etl.run_log (
    run_id bigserial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    start_date date,
    end_date date,
    source_rows integer,
    core_rows integer,
    quarantine_rows integer,
    outlier_rows integer,
    status varchar(16) NOT NULL,
    error text,
    CONSTRAINT etl_run_status CHECK (status IN ('running', 'success', 'failed'))
);

from __future__ import annotations

import os
from datetime import date

import pytest

pytest.importorskip("psycopg")

from etl.config import Settings
from etl.db import connect
from etl.pipeline import run_pipeline

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="database test is opt-in",
)

LO = 910000001
HI = 910000020
WINDOW_START = date(1999, 1, 1)
WINDOW_END = date(1999, 1, 2)
FX_DATE = date(2026, 10, 24)

COLUMNS = (
    "id",
    "loading_date",
    "loading_city_gcid",
    "unloading_city_gcid",
    "distance",
    "total_weight",
    "total_volume",
    "body_type",
    "price",
    "currency_code",
    "complex",
    "price_type",
    "is_fact",
    "nearest_rate_date",
    "outlier_mark",
    "weight_category",
    "volume_category",
    "source",
)


def _settings() -> Settings:
    return Settings(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "deals_bigdata"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        start_date=WINDOW_START,
        end_date=WINDOW_END,
        as_of=date(2026, 10, 26),
        log_level="INFO",
        train_model=False,
    )


def _row(price_id: int, **overrides) -> dict:
    row = {
        "id": price_id,
        "loading_date": WINDOW_START,
        "loading_city_gcid": 1001,
        "unloading_city_gcid": 1004,
        "distance": 500.0,
        "total_weight": 12.0,
        "total_volume": 50.0,
        "body_type": 56,
        "price": 80000.0,
        "currency_code": "643",
        "complex": False,
        "price_type": 3,
        "is_fact": True,
        "nearest_rate_date": FX_DATE,
        "outlier_mark": False,
        "weight_category": None,
        "volume_category": None,
        "source": "etl-test",
    }
    row.update(overrides)
    return row


def _fixtures() -> list[dict]:
    return [
        _row(910000001),
        _row(910000002, outlier_mark=True),
        _row(910000003, unloading_city_gcid=1001),
        _row(910000004, price=500),
        _row(910000005, price=0),
        _row(910000006, distance=0),
        _row(910000007, total_weight=-1),
        _row(910000008, loading_city_gcid=999999),
        _row(910000009, currency_code="840", price=100, nearest_rate_date=None),
        _row(910000010, currency_code="840", price=100),
        _row(910000011, currency_code="000", price=100),
        _row(910000012, total_weight=30, total_volume=120),
        _row(910000013, total_weight=10, total_volume=121),
        _row(910000014, total_weight=5, total_volume=0),
        _row(910000015, total_weight=2.5, total_volume=10),
        _row(910000016, total_weight=0.5, total_volume=10),
        _row(910000017, total_weight=0.4, total_volume=10),
        _row(910000018, total_volume=-1),
        _row(910000019, price=1000),
        _row(910000020, price=1000.01, price_type=6, is_fact=False, complex=True),
    ]


def _wipe(conn) -> None:
    conn.execute("DELETE FROM public.prices WHERE id BETWEEN %s AND %s", (LO, HI))
    ready = conn.execute(
        """
        SELECT to_regclass('core.prices') IS NOT NULL
           AND to_regclass('dq.quarantine_prices') IS NOT NULL
           AND to_regclass('etl.run_log') IS NOT NULL
        """
    ).fetchone()[0]
    if ready:
        conn.execute("DELETE FROM core.prices WHERE price_id BETWEEN %s AND %s", (LO, HI))
        conn.execute(
            "DELETE FROM dq.quarantine_prices WHERE price_id BETWEEN %s AND %s",
            (LO, HI),
        )
        conn.execute("DELETE FROM etl.run_log WHERE start_date = %s", (WINDOW_START,))
    conn.commit()


def _insert(conn, rows: list[dict]) -> None:
    statement = "INSERT INTO public.prices ({columns}) VALUES ({values})".format(
        columns=", ".join(COLUMNS),
        values=", ".join(["%s"] * len(COLUMNS)),
    )
    with conn.cursor() as cursor:
        cursor.executemany(statement, [tuple(row[column] for column in COLUMNS) for row in rows])
    conn.commit()


def _core(conn, price_id: int):
    return conn.execute(
        """
        SELECT weight_category, volume_category, outlier_mark, is_fact, complex,
               loading_city_gcid, unloading_city_gcid, price_rub, currency_code, price_type
        FROM core.prices
        WHERE price_id = %s
        """,
        (price_id,),
    ).fetchone()


def _reasons(conn, price_id: int) -> list[str]:
    found = conn.execute(
        "SELECT reason_codes FROM dq.quarantine_prices WHERE price_id = %s",
        (price_id,),
    ).fetchone()
    assert found is not None
    assert _core(conn, price_id) is None
    return list(found[0])


def _fingerprint(conn):
    return conn.execute(
        """
        SELECT
            (SELECT count(*) FROM core.prices WHERE price_id BETWEEN %s AND %s),
            (SELECT coalesce(sum(price_rub), 0) FROM core.prices WHERE price_id BETWEEN %s AND %s),
            (SELECT count(*) FROM dq.quarantine_prices WHERE price_id BETWEEN %s AND %s)
        """,
        (LO, HI, LO, HI, LO, HI),
    ).fetchone()


def test_window_load_quarantine_and_second_run():
    settings = _settings()
    assert settings.full_reload is False
    with connect(settings) as conn:
        assert conn.execute("SELECT count(*) FROM public.cities").fetchone()[0] > 0
        rate = conn.execute(
            """
            SELECT value
            FROM public.exchange_rates
            WHERE num_code = '840' AND setting_date = %s
            """,
            (FX_DATE,),
        ).fetchone()
        assert rate is not None
        fx_rate = float(rate[0])
        _wipe(conn)
        _insert(conn, _fixtures())
    try:
        first = run_pipeline(settings)
        with connect(settings) as conn:
            before = _fingerprint(conn)
        second = run_pipeline(settings)
        assert (first.source_rows, first.core_rows, first.quarantine_rows) == (
            second.source_rows,
            second.core_rows,
            second.quarantine_rows,
        )
        with connect(settings) as conn:
            assert _fingerprint(conn) == before
            valid = _core(conn, 910000001)
            assert valid is not None
            assert valid[0:2] == ("FTL", "FTL")
            assert valid[7] == pytest.approx(80000)
            outlier = _core(conn, 910000002)
            assert outlier is not None and outlier[2] is True
            same_city = _core(conn, 910000003)
            assert same_city is not None
            assert same_city[5] == same_city[6] == 1001
            assert _reasons(conn, 910000004) == ["RUB_PRICE_BELOW_MIN"]
            assert _reasons(conn, 910000005) == ["NON_POSITIVE_PRICE", "RUB_PRICE_BELOW_MIN"]
            assert _reasons(conn, 910000006) == ["NON_POSITIVE_DISTANCE"]
            assert _reasons(conn, 910000007) == ["NEGATIVE_WEIGHT"]
            assert _reasons(conn, 910000008) == ["UNKNOWN_LOADING_CITY"]
            assert _reasons(conn, 910000009) == ["MISSING_FX_RATE"]
            usd = _core(conn, 910000010)
            assert usd is not None
            assert usd[7] == pytest.approx(100 * fx_rate)
            assert usd[8] == "840"
            assert _reasons(conn, 910000011) == ["UNKNOWN_CURRENCY"]
            assert _core(conn, 910000012)[0:2] == ("G20T", "FTL")
            assert _core(conn, 910000013)[0:2] == ("FTL", "OTH")
            assert _core(conn, 910000014)[0:2] == ("10T", "OTH")
            assert _core(conn, 910000015)[0:2] == ("5T", "FTL")
            assert _core(conn, 910000016)[0:2] == ("L5T", "FTL")
            assert _core(conn, 910000017)[0:2] == ("OTH", "FTL")
            assert _reasons(conn, 910000018) == ["NEGATIVE_VOLUME"]
            assert _reasons(conn, 910000019) == ["RUB_PRICE_BELOW_MIN"]
            planned = _core(conn, 910000020)
            assert planned is not None
            assert planned[3] is False and planned[4] is True and planned[9] == 6
            assert _core(conn, 910000004) is None
            weight_gaps = conn.execute(
                """
                WITH sample(weight) AS (
                    VALUES (29.96::float8), (2.45::float8), (2.44::float8), (9.96::float8)
                ),
                expected AS (
                    SELECT
                        weight,
                        CASE
                            WHEN round(weight::numeric, 1) >= 30 THEN 'G20T'
                            WHEN round(weight::numeric, 1) >= 10 THEN 'FTL'
                            WHEN round(weight::numeric, 1) >= 5 THEN '10T'
                            WHEN round(weight::numeric, 1) >= 2.5 THEN '5T'
                            WHEN round(weight::numeric, 1) >= 0.5 THEN 'L5T'
                            ELSE 'OTH'
                        END AS category
                    FROM sample
                )
                SELECT e.weight::text, e.category, core.weight_category(e.weight)
                FROM expected e
                WHERE core.weight_category(e.weight) IS DISTINCT FROM e.category
                """
            ).fetchall()
            assert weight_gaps == []
            direct = conn.execute(
                """
                SELECT dq.price_reason_codes(0, '643', 10, 1, 1, true, true, true)
                """
            ).fetchone()[0]
            assert list(direct) == ["NON_POSITIVE_PRICE", "RUB_PRICE_BELOW_MIN"]
            city = conn.execute(
                """
                SELECT c.city_id, c.region_name, c.city_name
                FROM core.cities c
                WHERE c.gc_id = 1003
                """
            ).fetchone()
            source_min = conn.execute(
                "SELECT min(id) FROM public.cities WHERE gc_id = 1003"
            ).fetchone()[0]
            assert city[0] == source_min
            assert city[1] == "Республика Татарстан"
            assert city[2] == "Казань"
            assert conn.execute(
                "SELECT count(*) FROM core.cities WHERE gc_id = 1001"
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT body_group FROM core.body_types WHERE body_type_id = 57"
            ).fetchone()[0] == "Тент"
            assert conn.execute(
                "SELECT body_group FROM core.body_types WHERE body_type_id = 46"
            ).fetchone()[0] == "Рефрижератор"
            assert conn.execute(
                "SELECT body_group FROM core.body_types WHERE body_type_id = 1"
            ).fetchone()[0] == "Борт"
            assert conn.execute(
                "SELECT body_group FROM core.body_types WHERE body_type_id = 50"
            ).fetchone()[0] == "Прочие"
            columns = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'core' AND table_name = 'prices'
                    """
                )
            }
            assert "price_group_id" not in columns
            assert "price_rub" in columns
            logged = conn.execute(
                """
                SELECT status, source_rows
                FROM etl.run_log
                WHERE start_date = %s
                ORDER BY run_id DESC
                LIMIT 1
                """,
                (WINDOW_START,),
            ).fetchone()
            assert logged[0] == "success"
            assert logged[1] == len(_fixtures())
    finally:
        with connect(settings) as conn:
            _wipe(conn)

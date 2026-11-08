from __future__ import annotations

import os
import statistics
from datetime import date

import pytest

pytest.importorskip("psycopg")

from etl.config import Settings
from etl.db import connect
from etl.pipeline import apply_ddl, refresh_route_card

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="database test is opt-in",
)

AS_OF = date(2026, 10, 26)
ORIGIN = 9001
DEST = 9002
LO = 920000001
HI = 920004030

PUBLIC_COLUMNS = (
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
    "outlier_mark",
    "organization_id",
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
        start_date=date(1997, 1, 1),
        end_date=AS_OF,
        as_of=AS_OF,
        log_level="INFO",
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    weight = position - lower
    if lower >= len(ordered) - 1:
        return float(ordered[-1])
    return ordered[lower] * (1 - weight) + ordered[lower + 1] * weight


def _add(bucket, price_id, loading, price, **overrides):
    row = {
        "id": price_id,
        "loading_date": loading,
        "loading_city_gcid": ORIGIN,
        "unloading_city_gcid": DEST,
        "distance": 1000.0,
        "total_weight": 12.0,
        "total_volume": 40.0,
        "body_type": 56,
        "price": float(price),
        "currency_code": "643",
        "complex": False,
        "price_type": 3,
        "is_fact": True,
        "outlier_mark": False,
        "organization_id": 1,
        "weight_category": "FTL",
        "volume_category": "FTL",
        "source": "mart-test",
        "bodies": [56],
        "dates": [loading],
    }
    row.update(overrides)
    bucket.append(row)


def _fixtures() -> list[dict]:
    rows: list[dict] = []
    for offset, price in enumerate((100_000, 200_000, 300_000, 400_000)):
        _add(rows, 920000001 + offset, date(1998, 1, 10 + offset), price, organization_id=10 + offset)
    _add(rows, 920000010, date(1998, 2, 10), 500_000, organization_id=20)
    _add(rows, 920000020, date(1997, 1, 10), 125_000, organization_id=21)
    _add(
        rows,
        920000030,
        date(1998, 1, 10),
        110_000,
        weight_category="L5T",
        total_weight=1.0,
        bodies=[56, 57],
        dates=[date(1998, 1, 10), date(1998, 1, 20)],
        organization_id=30,
    )
    _add(
        rows,
        920000031,
        date(1998, 1, 12),
        220_000,
        weight_category="L5T",
        total_weight=1.0,
        bodies=[56, 15],
        organization_id=31,
    )
    _add(
        rows,
        920000032,
        date(1998, 1, 14),
        330_000,
        weight_category="L5T",
        total_weight=1.0,
        body_type=None,
        bodies=[],
        organization_id=32,
    )
    _add(rows, 920000040, date(1998, 1, 18), 9_000_000, outlier_mark=True, organization_id=40)
    _add(rows, 920000041, date(1998, 1, 18), 8_000_000, complex=True, organization_id=41)
    _add(
        rows,
        920000042,
        date(1998, 1, 18),
        7_000_000,
        is_fact=False,
        price_type=6,
        organization_id=42,
    )
    _add(
        rows,
        920000043,
        date(1998, 1, 5),
        160_000,
        body_type=2,
        bodies=[2],
        dates=[date(2026, 11, 15)],
        organization_id=43,
    )
    _add(
        rows,
        920000044,
        date(2026, 10, 20),
        150_000,
        body_type=2,
        bodies=[2],
        dates=[date(2026, 10, 20)],
        organization_id=44,
    )
    for index in range(30):
        _add(
            rows,
            920001001 + index,
            date(2026, 10, 10),
            80_000 + index * 100,
            weight_category="G20T",
            total_weight=30.0,
            price_type=3 if index < 5 else 1,
            organization_id=(index + 1) if index < 5 else 100,
        )
    for index in range(12):
        _add(
            rows,
            920002001 + index,
            date(2024, 1, 15),
            60_000 + index * 100,
            weight_category="5T",
            total_weight=3.0,
            organization_id=(index % 5) + 1,
        )
    for index in range(9):
        _add(
            rows,
            920003001 + index,
            date(2026, 10, 10),
            50_000 + index * 100,
            weight_category="10T",
            total_weight=6.0,
            organization_id=index + 1,
        )
    for index in range(30):
        _add(
            rows,
            920004001 + index,
            date(2026, 10, 10),
            70_000 + index * 100,
            body_type=15,
            bodies=[15],
            price_type=3 if index < 4 else 1,
            organization_id=(index + 1) if index < 4 else 50,
        )
    return rows


def _seed(conn, rows: list[dict]) -> None:
    conn.execute(
        """
        INSERT INTO core.cities (
            city_id, gc_id, name, full_name_local, city_name, region_name, latitude, longitude
        )
        VALUES
            (900001, 9001, 'Тест-А', 'Тест-А, Тестовая обл.', 'Тест-А', 'Тестовая обл.', 0, 0),
            (900002, 9002, 'Тест-Б', 'Тест-Б, Тестовая обл.', 'Тест-Б', 'Тестовая обл.', 1, 1)
        """
    )
    public_sql = "INSERT INTO public.prices ({columns}) VALUES ({values})".format(
        columns=", ".join(PUBLIC_COLUMNS),
        values=", ".join(["%s"] * len(PUBLIC_COLUMNS)),
    )
    core_sql = """
        INSERT INTO core.prices (
            price_id, loading_date, loading_city_gcid, unloading_city_gcid, distance,
            total_weight, total_volume, weight_category, volume_category, body_type,
            price_src, currency_code, fx_rate, price_rub, price_type, is_fact, complex,
            organization_id, outlier_mark, source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cursor:
        cursor.executemany(
            public_sql,
            [tuple(row[column] for column in PUBLIC_COLUMNS) for row in rows],
        )
        cursor.executemany(
            core_sql,
            [
                (
                    row["id"],
                    row["loading_date"],
                    row["loading_city_gcid"],
                    row["unloading_city_gcid"],
                    row["distance"],
                    row["total_weight"],
                    row["total_volume"],
                    row["weight_category"],
                    row["volume_category"],
                    row["body_type"],
                    row["price"],
                    row["currency_code"],
                    row["price"],
                    row["price_type"],
                    row["is_fact"],
                    row["complex"],
                    row["organization_id"],
                    row["outlier_mark"],
                    row["source"],
                )
                for row in rows
            ],
        )
        cursor.executemany(
            "INSERT INTO public.price_body_types (price_id, body_type_id) VALUES (%s, %s)",
            [(row["id"], body_id) for row in rows for body_id in row["bodies"]],
        )
        cursor.executemany(
            "INSERT INTO public.price_dates (price_id, price_date) VALUES (%s, %s)",
            [(row["id"], price_date) for row in rows for price_date in row["dates"]],
        )


def _cell(conn, month: date, body: str, weight: str):
    return conn.execute(
        """
        SELECT
            trips_count, carriers_count, p25_trip, median_trip, p75_trip, avg_trip,
            p25_km, median_km, p75_km, cv_rate, mom_pct, yoy_pct, reliability_level,
            loading_city_name, unloading_city_name, loading_region_name, last_price_date
        FROM mart.route_card
        WHERE loading_city_gcid = %s
          AND unloading_city_gcid = %s
          AND month_date = %s
          AND body_group = %s
          AND weight_category = %s
        """,
        (ORIGIN, DEST, month, body, weight),
    ).fetchone()


def test_route_card_corridor_dedup_and_trust():
    prices = [100_000.0, 200_000.0, 300_000.0, 400_000.0]
    conn = connect(_settings())
    try:
        assert conn.execute("SELECT count(*) FROM core.cities").fetchone()[0] > 0
        apply_ddl(conn)
        _seed(conn, _fixtures())
        first_rows = refresh_route_card(conn, AS_OF)
        fingerprint = conn.execute(
            """
            SELECT count(*), coalesce(sum(median_trip), 0)
            FROM mart.route_card
            WHERE loading_city_gcid = %s
            """,
            (ORIGIN,),
        ).fetchone()
        assert refresh_route_card(conn, AS_OF) == first_rows
        assert (
            conn.execute(
                """
                SELECT count(*), coalesce(sum(median_trip), 0)
                FROM mart.route_card
                WHERE loading_city_gcid = %s
                """,
                (ORIGIN,),
            ).fetchone()
            == fingerprint
        )
        january = _cell(conn, date(1998, 1, 1), "Тент", "FTL")
        assert january is not None
        (
            trips, carriers, p25, median, p75, avg_trip,
            p25_km, median_km, p75_km, cv_rate, mom, yoy, level,
            origin_name, dest_name, region_name, last_date,
        ) = january
        assert trips == 4
        assert carriers == 4
        assert p25 == pytest.approx(_percentile(prices, 0.25))
        assert median == pytest.approx(_percentile(prices, 0.50))
        assert p75 == pytest.approx(_percentile(prices, 0.75))
        assert avg_trip == pytest.approx(250_000)
        assert p25_km == pytest.approx(_percentile(prices, 0.25) / 1000)
        assert median_km == pytest.approx(250)
        assert p75_km == pytest.approx(_percentile(prices, 0.75) / 1000)
        assert cv_rate == pytest.approx(statistics.stdev(prices) / statistics.mean(prices))
        assert mom is None
        assert yoy == pytest.approx(100)
        assert level == "LOW_DATA"
        assert origin_name == "Тест-А"
        assert dest_name == "Тест-Б"
        assert region_name == "Тестовая обл."
        assert last_date == date(1998, 1, 13)
        february = _cell(conn, date(1998, 2, 1), "Тент", "FTL")
        assert february is not None
        assert february[0] == 1
        assert february[3] == pytest.approx(500_000)
        assert february[9] is None
        assert february[10] == pytest.approx(100)
        assert february[11] is None
        assert february[12] == "LOW_DATA"
        prior = _cell(conn, date(1997, 1, 1), "Тент", "FTL")
        assert prior is not None
        assert prior[3] == pytest.approx(125_000)
        assert prior[10] is None
        assert prior[11] is None
        tent = _cell(conn, date(1998, 1, 1), "Тент", "L5T")
        board = _cell(conn, date(1998, 1, 1), "Борт", "L5T")
        missing = _cell(conn, date(1998, 1, 1), "Не указан", "L5T")
        assert tent is not None and tent[0] == 2
        assert tent[3] == pytest.approx(165_000)
        assert tent[16] == date(1998, 1, 20)
        assert board is not None and board[0] == 1 and board[3] == pytest.approx(220_000)
        assert missing is not None and missing[0] == 1 and missing[3] == pytest.approx(330_000)
        october = _cell(conn, date(2026, 10, 1), "Изотерм", "FTL")
        assert october is not None and october[0] == 1 and october[12] == "LOW_DATA"
        assert (
            conn.execute(
                """
                SELECT count(*)
                FROM mart.route_card
                WHERE loading_city_gcid = %s AND month_date = DATE '2026-11-01'
                """,
                (ORIGIN,),
            ).fetchone()[0]
            == 0
        )
        high = _cell(conn, date(2026, 10, 1), "Тент", "G20T")
        stale = _cell(conn, date(2024, 1, 1), "Тент", "5T")
        thin = _cell(conn, date(2026, 10, 1), "Тент", "10T")
        few_carriers = _cell(conn, date(2026, 10, 1), "Борт", "FTL")
        assert high is not None and high[0] == 30 and high[1] == 5 and high[12] == "HIGH"
        assert stale is not None and stale[0] == 12 and stale[1] == 5 and stale[12] == "MEDIUM"
        assert thin is not None and thin[0] == 9 and thin[12] == "LOW_DATA"
        assert few_carriers is not None and few_carriers[0] == 30 and few_carriers[1] == 4
        assert few_carriers[12] == "MEDIUM"
        assert LO <= 920000001 <= HI
    finally:
        conn.rollback()
        conn.close()

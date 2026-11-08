from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from etl.config import Settings
from etl.db import connect
from etl.log import log_event
from etl.sql_script import split_sql

ROOT = Path(__file__).resolve().parents[1]
DWH_SQL = ROOT / "sql" / "dwh"
ETL_SQL = ROOT / "etl" / "sql"
STEPS = (
    "000_dimensions.sql",
    "005_bounds.sql",
    "010_classify.sql",
    "020_delete_window.sql",
    "030_insert_core.sql",
    "040_insert_quarantine.sql",
)
LOCK_KEY = "de_interviews.etl"
LOGGER = logging.getLogger("etl")


@dataclass(frozen=True)
class RunSummary:
    run_id: int
    source_rows: int
    core_rows: int
    quarantine_rows: int
    outlier_rows: int
    same_city_rows: int
    null_body_rows: int
    snapshot_day_rows: int
    snapshot_day_outlier_rows: int
    core_table_rows: int
    quarantine_table_rows: int
    mart_rows: int
    reasons: tuple[tuple[str, int], ...]


def execute_sql_file(conn, path: Path) -> None:
    for statement in split_sql(path.read_text(encoding="utf-8")):
        conn.execute(statement)


def apply_ddl(conn) -> None:
    for path in sorted(DWH_SQL.glob("*.sql")):
        execute_sql_file(conn, path)


def _scalar(conn, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def _collect(conn) -> tuple[RunSummary, dict[str, int]]:
    batch = conn.execute(
        """
        SELECT
            count(*) AS source_rows,
            count(*) FILTER (WHERE cardinality(reason_codes) = 0) AS core_rows,
            count(*) FILTER (WHERE cardinality(reason_codes) > 0) AS quarantine_rows,
            count(*) FILTER (WHERE cardinality(reason_codes) = 0 AND outlier_mark) AS outlier_rows,
            count(*) FILTER (
                WHERE cardinality(reason_codes) = 0
                  AND loading_city_gcid = unloading_city_gcid
            ) AS same_city_rows,
            count(*) FILTER (WHERE cardinality(reason_codes) = 0 AND body_type IS NULL) AS null_body_rows,
            count(*) FILTER (
                WHERE cardinality(reason_codes) = 0
                  AND created_at >= TIMESTAMP '2026-10-26'
                  AND created_at < TIMESTAMP '2026-10-27'
            ) AS snapshot_day_rows,
            count(*) FILTER (
                WHERE cardinality(reason_codes) = 0
                  AND created_at >= TIMESTAMP '2026-10-26'
                  AND created_at < TIMESTAMP '2026-10-27'
                  AND outlier_mark
            ) AS snapshot_day_outlier_rows
        FROM etl_classified
        """
    ).fetchone()
    reasons = tuple(
        (str(code), int(rows))
        for code, rows in conn.execute(
            """
            SELECT code, count(*)
            FROM etl_classified
            CROSS JOIN LATERAL unnest(reason_codes) AS code
            GROUP BY code
            ORDER BY code
            """
        ).fetchall()
    )
    window = """
        (b.start_date IS NULL OR {alias}.loading_date >= b.start_date)
        AND (b.end_date IS NULL OR {alias}.loading_date <= b.end_date)
    """
    counts = {
        "source_rows": int(batch[0]),
        "core_rows": int(batch[1]),
        "quarantine_rows": int(batch[2]),
        "outlier_rows": int(batch[3]),
        "same_city_rows": int(batch[4]),
        "null_body_rows": int(batch[5]),
        "snapshot_day_rows": int(batch[6]),
        "snapshot_day_outlier_rows": int(batch[7]),
        "core_match": _scalar(
            conn,
            """
            SELECT count(*)
            FROM core.prices p
            WHERE p.price_id IN (
                SELECT c.price_id FROM etl_classified c WHERE cardinality(c.reason_codes) = 0
            )
            """,
        ),
        "quarantine_match": _scalar(
            conn,
            """
            SELECT count(*)
            FROM dq.quarantine_prices q
            WHERE q.price_id IN (
                SELECT c.price_id FROM etl_classified c WHERE cardinality(c.reason_codes) > 0
            )
            """,
        ),
        "core_leftover": _scalar(
            conn,
            f"""
            SELECT count(*)
            FROM core.prices p
            CROSS JOIN etl_bounds b
            WHERE {window.format(alias="p")}
              AND NOT EXISTS (
                  SELECT 1
                  FROM etl_classified c
                  WHERE c.price_id = p.price_id
                    AND cardinality(c.reason_codes) = 0
              )
            """,
        ),
        "quarantine_leftover": _scalar(
            conn,
            f"""
            SELECT count(*)
            FROM dq.quarantine_prices q
            CROSS JOIN etl_bounds b
            WHERE {window.format(alias="q")}
              AND NOT EXISTS (
                  SELECT 1
                  FROM etl_classified c
                  WHERE c.price_id = q.price_id
                    AND cardinality(c.reason_codes) > 0
              )
            """,
        ),
        "overlap": _scalar(
            conn,
            """
            SELECT count(*)
            FROM core.prices c
            JOIN dq.quarantine_prices q ON q.price_id = c.price_id
            """,
        ),
        "core_table_rows": _scalar(conn, "SELECT count(*) FROM core.prices"),
        "quarantine_table_rows": _scalar(conn, "SELECT count(*) FROM dq.quarantine_prices"),
    }
    summary = RunSummary(
        run_id=0,
        source_rows=counts["source_rows"],
        core_rows=counts["core_rows"],
        quarantine_rows=counts["quarantine_rows"],
        outlier_rows=counts["outlier_rows"],
        same_city_rows=counts["same_city_rows"],
        null_body_rows=counts["null_body_rows"],
        snapshot_day_rows=counts["snapshot_day_rows"],
        snapshot_day_outlier_rows=counts["snapshot_day_outlier_rows"],
        core_table_rows=counts["core_table_rows"],
        quarantine_table_rows=counts["quarantine_table_rows"],
        mart_rows=0,
        reasons=reasons,
    )
    return summary, counts


def _ensure_invariants(summary: RunSummary, counts: dict[str, int]) -> None:
    problems: list[str] = []
    if summary.core_rows + summary.quarantine_rows != summary.source_rows:
        problems.append(
            f"classified split {summary.core_rows}+{summary.quarantine_rows} != {summary.source_rows}"
        )
    if counts["core_match"] != summary.core_rows:
        problems.append(f"core landed {counts['core_match']} != clean {summary.core_rows}")
    if counts["quarantine_match"] != summary.quarantine_rows:
        problems.append(
            f"quarantine landed {counts['quarantine_match']} != rejected {summary.quarantine_rows}"
        )
    if counts["core_leftover"] != 0:
        problems.append(f"core leftover in window {counts['core_leftover']}")
    if counts["quarantine_leftover"] != 0:
        problems.append(f"quarantine leftover in window {counts['quarantine_leftover']}")
    if counts["overlap"] != 0:
        problems.append(f"price_id in both core and quarantine {counts['overlap']}")
    if problems:
        raise RuntimeError("etl invariant failed: " + "; ".join(problems))


def _start_run(conn, settings: Settings) -> int:
    row = conn.execute(
        """
        INSERT INTO etl.run_log (start_date, end_date, status)
        VALUES (%s, %s, 'running')
        RETURNING run_id
        """,
        (settings.start_date, settings.end_date),
    ).fetchone()
    return int(row[0])


def _mark_success(conn, run_id: int, summary: RunSummary) -> None:
    conn.execute(
        """
        UPDATE etl.run_log
        SET finished_at = clock_timestamp(),
            source_rows = %s,
            core_rows = %s,
            quarantine_rows = %s,
            outlier_rows = %s,
            mart_rows = %s,
            status = 'success',
            error = NULL
        WHERE run_id = %s
        """,
        (
            summary.source_rows,
            summary.core_rows,
            summary.quarantine_rows,
            summary.outlier_rows,
            summary.mart_rows,
            run_id,
        ),
    )


def refresh_route_card(conn, as_of: date) -> int:
    execute_sql_file(conn, ETL_SQL / "050_as_of.sql")
    conn.execute("INSERT INTO etl_as_of (as_of_date) VALUES (%s)", (as_of,))
    execute_sql_file(conn, ETL_SQL / "051_refresh_mart.sql")
    _ensure_mart(conn)
    return _scalar(conn, "SELECT count(*) FROM mart.route_card")


def _ensure_mart(conn) -> None:
    broken = _scalar(
        conn,
        """
        SELECT count(*)
        FROM mart.route_card
        WHERE last_price_date > as_of_date
           OR month_date <> date_trunc('month', last_price_date)::date
           OR carriers_count > trips_count
           OR p25_trip > median_trip
           OR median_trip > p75_trip
           OR p25_km > median_km
           OR median_km > p75_km
           OR (
                reliability_level = 'HIGH'
                AND NOT (
                    trips_count >= 30
                    AND carriers_count >= 5
                    AND (as_of_date - last_price_date) <= 30
                )
           )
           OR (
                reliability_level = 'MEDIUM'
                AND (
                    trips_count < 10
                    OR (
                        trips_count >= 30
                        AND carriers_count >= 5
                        AND (as_of_date - last_price_date) <= 30
                    )
                )
           )
           OR (reliability_level = 'LOW_DATA' AND trips_count >= 10)
        """,
    )
    if broken:
        raise RuntimeError(f"mart invariant failed for {broken} route cards")


def _mark_failed(conn, run_id: int, exc: Exception) -> None:
    conn.rollback()
    conn.execute(
        """
        UPDATE etl.run_log
        SET finished_at = clock_timestamp(),
            status = 'failed',
            error = %s
        WHERE run_id = %s
        """,
        (str(exc)[:4000], run_id),
    )
    conn.commit()


def _show_date(value) -> str:
    if value is None:
        return "all"
    return value.isoformat()


def _unlock(conn) -> None:
    try:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s)::bigint)", (LOCK_KEY,))
        conn.commit()
    except Exception:
        LOGGER.exception("event=advisory_unlock_failed")


def run_pipeline(settings: Settings) -> RunSummary:
    log_event(
        "etl_start",
        full_reload=settings.full_reload,
        start_date=_show_date(settings.start_date),
        end_date=_show_date(settings.end_date),
        dbname=settings.dbname,
        host=settings.host,
    )
    with connect(settings, attempts=30) as conn:
        conn.execute("SET lock_timeout = '60s'")
        conn.execute("SET statement_timeout = '30min'")
        conn.execute("SELECT pg_advisory_lock(hashtext(%s)::bigint)", (LOCK_KEY,))
        try:
            apply_ddl(conn)
            conn.commit()
            run_id = _start_run(conn, settings)
            conn.commit()
            try:
                with conn.transaction():
                    for name in STEPS:
                        execute_sql_file(conn, ETL_SQL / name)
                        if name == "005_bounds.sql":
                            conn.execute(
                                "INSERT INTO etl_bounds (start_date, end_date) VALUES (%s, %s)",
                                (settings.start_date, settings.end_date),
                            )
                    summary, counts = _collect(conn)
                    _ensure_invariants(summary, counts)
                    mart_rows = refresh_route_card(conn, settings.as_of)
                    if settings.train_model:
                        from ml.train import train_and_score

                        train_and_score(conn, settings.as_of)
                    summary = RunSummary(
                        run_id=run_id,
                        source_rows=summary.source_rows,
                        core_rows=summary.core_rows,
                        quarantine_rows=summary.quarantine_rows,
                        outlier_rows=summary.outlier_rows,
                        same_city_rows=summary.same_city_rows,
                        null_body_rows=summary.null_body_rows,
                        snapshot_day_rows=summary.snapshot_day_rows,
                        snapshot_day_outlier_rows=summary.snapshot_day_outlier_rows,
                        core_table_rows=summary.core_table_rows,
                        quarantine_table_rows=summary.quarantine_table_rows,
                        mart_rows=mart_rows,
                        reasons=summary.reasons,
                    )
                    _mark_success(conn, run_id, summary)
            except Exception as exc:
                LOGGER.exception("event=etl_failed")
                try:
                    _mark_failed(conn, run_id, exc)
                except Exception:
                    LOGGER.exception("event=run_log_update_failed")
                raise
            try:
                conn.execute("ANALYZE core.cities")
                conn.execute("ANALYZE core.body_types")
                conn.execute("ANALYZE core.prices")
                conn.execute("ANALYZE dq.quarantine_prices")
                conn.execute("ANALYZE mart.route_card")
                if settings.train_model:
                    conn.execute("ANALYZE mart.ml_price_predictions")
                    conn.execute("ANALYZE mart.ml_model_metrics")
                conn.commit()
            except Exception:
                LOGGER.exception("event=analyze_failed")
                conn.rollback()
        finally:
            _unlock(conn)
    reason_text = " ".join(f"{code}={rows}" for code, rows in summary.reasons) or "none=0"
    log_event(
        "etl_finished",
        run_id=summary.run_id,
        source_rows=summary.source_rows,
        core_rows=summary.core_rows,
        quarantine_rows=summary.quarantine_rows,
        outlier_rows=summary.outlier_rows,
        same_city_rows=summary.same_city_rows,
        null_body_rows=summary.null_body_rows,
        snapshot_day_rows=summary.snapshot_day_rows,
        snapshot_day_outlier_rows=summary.snapshot_day_outlier_rows,
        core_table_rows=summary.core_table_rows,
        quarantine_table_rows=summary.quarantine_table_rows,
        mart_rows=summary.mart_rows,
        as_of=_show_date(settings.as_of),
        reasons=reason_text,
    )
    return summary

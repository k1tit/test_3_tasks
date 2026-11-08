from __future__ import annotations

from etl.config import load_settings
from etl.db import connect
from etl.log import configure_logging
from etl.pipeline import apply_ddl
from ml.train import train_and_score


def main(argv: list[str] | None = None) -> None:
    try:
        settings = load_settings(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    configure_logging(settings.log_level)
    with connect(settings, attempts=30) as conn:
        conn.execute("SET lock_timeout = '60s'")
        conn.execute("SET statement_timeout = '30min'")
        apply_ddl(conn)
        conn.commit()
        try:
            with conn.transaction():
                train_and_score(conn, settings.as_of)
        except Exception as exc:
            raise SystemExit(1) from exc
        conn.execute("ANALYZE mart.ml_price_predictions")
        conn.execute("ANALYZE mart.ml_model_metrics")
        conn.commit()


if __name__ == "__main__":
    main()

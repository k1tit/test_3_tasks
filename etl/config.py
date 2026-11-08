from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    start_date: date | None
    end_date: date | None
    as_of: date
    log_level: str
    train_model: bool = True

    @property
    def full_reload(self) -> bool:
        return self.start_date is None and self.end_date is None


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def resolve_window(
    cli_start: str | None,
    cli_end: str | None,
    env_start: str | None,
    env_end: str | None,
) -> tuple[date | None, date | None]:
    cli_start = _blank(cli_start)
    cli_end = _blank(cli_end)
    env_start = _blank(env_start)
    env_end = _blank(env_end)
    if (cli_start is None) != (cli_end is None):
        raise ValueError("start_date and end_date must be passed together")
    if cli_start is None:
        start_raw, end_raw = env_start, env_end
    else:
        start_raw, end_raw = cli_start, cli_end
    if (start_raw is None) != (end_raw is None):
        raise ValueError("start_date and end_date must be set together")
    if start_raw is None or end_raw is None:
        return None, None
    start = date.fromisoformat(start_raw)
    end = date.fromisoformat(end_raw)
    if start > end:
        raise ValueError("start_date is after end_date")
    return start, end


def resolve_as_of(raw: str | None) -> date:
    cleaned = _blank(raw)
    if cleaned is None:
        return date(2026, 10, 26)
    return date.fromisoformat(cleaned)


def load_settings(argv: list[str] | None = None) -> Settings:
    import argparse

    parser = argparse.ArgumentParser(prog="etl")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--as-of")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)
    start_date, end_date = resolve_window(
        args.start_date,
        args.end_date,
        os.getenv("ETL_START_DATE"),
        os.getenv("ETL_END_DATE"),
    )
    return Settings(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "deals_bigdata"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        start_date=start_date,
        end_date=end_date,
        as_of=resolve_as_of(args.as_of if args.as_of is not None else os.getenv("AS_OF_DATE")),
        log_level=args.log_level,
    )

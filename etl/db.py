from __future__ import annotations

import time

import psycopg

from etl.config import Settings


def connect(settings: Settings, *, attempts: int = 1, delay_seconds: float = 2.0) -> psycopg.Connection:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return psycopg.connect(
                host=settings.host,
                port=settings.port,
                dbname=settings.dbname,
                user=settings.user,
                password=settings.password,
                connect_timeout=5,
            )
        except psycopg.OperationalError as exc:
            last = exc
            if attempt == attempts:
                break
            time.sleep(delay_seconds)
    assert last is not None
    raise last

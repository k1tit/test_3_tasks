from __future__ import annotations

from etl.config import load_settings
from etl.log import configure_logging
from etl.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> None:
    try:
        settings = load_settings(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    configure_logging(settings.log_level)
    try:
        run_pipeline(settings)
    except Exception as exc:
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

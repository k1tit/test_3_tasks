from __future__ import annotations

import calendar
from datetime import date, timedelta

TRAIN_MONTHS = 3
TEST_DAYS = 21


def minus_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def split_bounds(as_of: date) -> tuple[date, date]:
    return minus_months(as_of, TRAIN_MONTHS), as_of - timedelta(days=TEST_DAYS)


def assign_split(loading_date: date, as_of: date) -> str:
    train_start, test_start = split_bounds(as_of)
    if loading_date > as_of:
        return "future"
    if test_start <= loading_date <= as_of:
        return "test"
    if train_start <= loading_date < test_start:
        return "train"
    return "ignore"

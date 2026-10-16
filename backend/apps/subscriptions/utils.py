"""Subscription Domain Utilities.

Provides date and calendar-month calculation utilities for subscription billing cycles and trials.
"""

import calendar
from datetime import datetime, timedelta

from apps.plans.models import BillingInterval


def add_calendar_months(dt: datetime, months: int) -> datetime:
    """Add `months` calendar months to datetime `dt`, clamping the day to the last day of the target month if needed."""
    month_0 = (dt.month - 1) + months
    year = dt.year + (month_0 // 12)
    month = (month_0 % 12) + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)


def get_interval_months(billing_interval: str) -> int:
    """Map billing interval string to the number of calendar months.

    - monthly -> 1
    - quarterly -> 3
    - annual -> 12
    """
    if billing_interval == BillingInterval.MONTHLY or billing_interval == "monthly":
        return 1
    elif billing_interval == BillingInterval.QUARTERLY or billing_interval == "quarterly":
        return 3
    elif billing_interval == BillingInterval.ANNUAL or billing_interval == "annual":
        return 12
    else:
        raise ValueError(f"Unsupported billing interval: '{billing_interval}'")


def calculate_period_end(start_dt: datetime, billing_interval: str) -> datetime:
    """Calculate the period end datetime based on billing interval using get_interval_months."""
    months = get_interval_months(billing_interval)
    return add_calendar_months(start_dt, months)


def calculate_trial_end(start_dt: datetime, trial_days: int = 14) -> datetime:
    """Calculate the trial end datetime based on trial days (defaults to 14 days)."""
    if trial_days <= 0:
        raise ValueError("trial_days must be greater than 0.")
    return start_dt + timedelta(days=trial_days)

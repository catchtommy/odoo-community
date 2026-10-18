# -*- coding: utf-8 -*-
"""
Centralised timezone utilities for the tuition_management module.

All timezone Selection fields should use COMMON_TIMEZONES as their
``selection`` source so the list, labels and ordering are consistent
across every form.  The label includes the current UTC offset so users
can see at a glance which offset applies (e.g. "Asia/Kolkata (UTC+05:30)").
"""

from datetime import datetime
import pytz


def _build_tz_selection():
    """
    Return a list of (value, label) pairs for all common pytz timezones,
    sorted first by UTC offset (ascending) then alphabetically.
    Each label has the format: "Region/City (UTC+HH:MM)".
    """
    now = datetime.utcnow()
    results = []
    for tz_name in pytz.common_timezones:
        tz = pytz.timezone(tz_name)
        offset = tz.utcoffset(now)
        total_seconds = int(offset.total_seconds())
        sign = '+' if total_seconds >= 0 else '-'
        abs_sec = abs(total_seconds)
        hours, remainder = divmod(abs_sec, 3600)
        minutes = remainder // 60
        label = f"{tz_name} (UTC{sign}{hours:02d}:{minutes:02d})"
        results.append((total_seconds, tz_name, label))

    results.sort(key=lambda x: (x[0], x[1]))
    return [(tz_name, label) for _, tz_name, label in results]


# Computed once at module load time — reused by all Selection fields.
COMMON_TIMEZONES = _build_tz_selection()

# Default timezone used when no user preference is found.
DEFAULT_TIMEZONE = 'US/Eastern'


def get_tz_selection(self=None):
    """Return the common timezone selection list (for use in field ``selection=``).

    Odoo calls selection callables with the recordset as the first positional
    argument, so we accept (and ignore) it.

    Usage in a model::

        from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE

        timezone = fields.Selection(
            selection=get_tz_selection,
            string='Timezone',
            default=DEFAULT_TIMEZONE,
        )
    """
    return COMMON_TIMEZONES


def tz_abbr(tz_name, utc_dt=None):
    """Short code for tz_name at the given naive-UTC moment (default: now),
    e.g. IST, EST/EDT, GMT/BST. Zones with no letter code get "UTC+04"."""
    try:
        tz = pytz.timezone(tz_name or 'UTC')
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc
    utc_dt = utc_dt or datetime.utcnow()
    abbr = pytz.utc.localize(utc_dt).astimezone(tz).strftime('%Z')
    if abbr[:1] in '+-':
        abbr = 'UTC' + abbr
    return abbr


def format_local_dt(utc_dt, tz_name, fmt='%d %b %Y, %H:%M'):
    """Format a naive-UTC datetime in tz_name, suffixed with its short code."""
    try:
        tz = pytz.timezone(tz_name or 'UTC')
    except pytz.UnknownTimeZoneError:
        tz_name, tz = 'UTC', pytz.utc
    local_dt = pytz.utc.localize(utc_dt).astimezone(tz)
    return '%s %s' % (local_dt.strftime(fmt), tz_abbr(tz_name, utc_dt))

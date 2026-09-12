"""Boot script — runs once on power-on.

Runs before ``main.py``; keep it minimal (RTC / clock sync only).
"""

from nettime import sync as sync_time

sync_time("pool.ntp.org")
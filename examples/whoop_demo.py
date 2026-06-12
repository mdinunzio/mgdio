"""Whoop end-to-end demo for the mgdio package.

Run this after installing mgdio and completing the one-time setup
(``uv run mgdio auth whoop``).

Walks through the read surface:

1. Profile + body measurements.
2. Last 7 recovery records (score, HRV, resting HR).
3. Last 7 sleep records (performance %, respiratory rate).
4. Last 7 workouts (sport, strain, calories).
5. Last 7 cycles (day strain).

Whoop is read-only -- this script changes nothing.

Usage:
    uv run python examples/whoop_demo.py
"""

from __future__ import annotations

from mgdio.whoop import (
    fetch_body_measurement,
    fetch_cycles,
    fetch_profile,
    fetch_recoveries,
    fetch_sleeps,
    fetch_workouts,
)


def _fmt(value, suffix: str = "", *, nd: int = 0) -> str:
    """Format a possibly-None numeric Whoop field."""
    if value is None:
        return "--"
    if nd:
        return f"{value:.{nd}f}{suffix}"
    return f"{value:g}{suffix}"


def main() -> None:
    """Run the Whoop read-only demo."""
    print("== 1. Profile + body ==")
    profile = fetch_profile()
    print(f"   {profile.first_name} {profile.last_name}  <{profile.email}>")
    body = fetch_body_measurement()
    print(
        f"   {_fmt(body.height_meter, ' m', nd=2)}, "
        f"{_fmt(body.weight_kilogram, ' kg', nd=1)}, "
        f"max HR {_fmt(body.max_heart_rate, ' bpm')}"
    )

    print("\n== 2. Recent recovery (morning metric) ==")
    recoveries = fetch_recoveries(max_records=7)
    if not recoveries:
        print("   (none yet -- recovery appears after the night's sleep closes)")
    for r in recoveries:
        when = f"{r.created_at:%Y-%m-%d}" if r.created_at else "?"
        print(
            f"   {when}  recovery {_fmt(r.recovery_score, '%'):>5}  "
            f"hrv {_fmt(r.hrv_rmssd_milli, 'ms', nd=1):>8}  "
            f"rhr {_fmt(r.resting_heart_rate, 'bpm'):>7}"
        )

    print("\n== 3. Recent sleep ==")
    for s in fetch_sleeps(max_records=7):
        when = f"{s.start:%Y-%m-%d %H:%M}" if s.start else "?"
        nap = " (nap)" if s.nap else ""
        print(
            f"   {when}  performance "
            f"{_fmt(s.sleep_performance_percentage, '%'):>5}  "
            f"resp {_fmt(s.respiratory_rate, '/min', nd=1):>8}{nap}"
        )

    print("\n== 4. Recent workouts ==")
    for w in fetch_workouts(max_records=7):
        when = f"{w.start:%Y-%m-%d %H:%M}" if w.start else "?"
        sport = w.sport_name or "workout"
        print(
            f"   {when}  {sport[:18]:18}  strain {_fmt(w.strain, nd=1):>5}  "
            f"{_fmt(w.calories, ' kcal', nd=0):>9}"
        )

    print("\n== 5. Recent cycles (day strain) ==")
    for c in fetch_cycles(max_records=7):
        when = f"{c.start:%Y-%m-%d}" if c.start else "?"
        print(f"   {when}  day strain {_fmt(c.strain, nd=1):>5}")

    print("\nDone.")


if __name__ == "__main__":
    main()

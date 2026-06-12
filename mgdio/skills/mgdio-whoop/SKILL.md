---
name: mgdio-whoop
description: Read Whoop fitness/recovery data via the `mgdio whoop` CLI. Use
  this when the user asks about their Whoop recovery score, HRV, resting
  heart rate, how they slept (sleep performance, respiratory rate),
  their workouts or strain, day strain (cycles), or their Whoop
  profile/body measurements. Read-only; all data comes from the Whoop
  v2 API with auth handled automatically.
---

# mgdio Whoop

Read recovery, sleep, workout, cycle, profile, and body-measurement data
from the user's Whoop account via the `mgdio` CLI.

## Prerequisite

The user must have authenticated once: `mgdio auth whoop`. This opens a
local page where they paste their Whoop app's Client ID + Secret and
authorize. If a command fails with an auth error, tell them to run that.
The redirect URI defaults to `http://localhost:8765/callback` and can be
overridden with the `MGDIO_WHOOP_REDIRECT_URI` env var (must match the
Whoop app registration).

## Safety contract

The Whoop integration is **read-only** -- there are no write/update/delete
operations, so nothing here needs confirmation. (For consistency with the
other mgdio skills: any write operation MUST be confirmed with the user
before invocation -- but Whoop exposes none.)

## CLI: read

```bash
# Recovery (score %, HRV in ms, resting HR). Recovery is a MORNING metric:
# a record doesn't exist until the night's sleep cycle closes, so "today"
# may be empty before the user has woken up.
mgdio whoop recoveries --max 7

# Sleep (performance %, naps flagged)
mgdio whoop sleeps --max 7

# Workouts (sport, strain, calories)
mgdio whoop workouts --max 7

# Physiological cycles (day strain)
mgdio whoop cycles --max 7

# Profile + body measurements (single record each)
mgdio whoop profile
mgdio whoop body
```

The collection commands (`recoveries`, `sleeps`, `workouts`, `cycles`)
accept `--max N` (default 10) and optional `--start` / `--end` ISO
datetimes. **Datetimes must include a timezone offset** (e.g.
`2026-05-01T00:00:00-04:00` or `...Z`); naive values are rejected.

```bash
mgdio whoop sleeps --start "2026-05-01T00:00:00-04:00" \
  --end "2026-05-12T00:00:00-04:00" --max 25
```

## Python (when chaining is needed)

```python
from datetime import datetime, timezone
from mgdio.whoop import (
    fetch_recoveries, fetch_sleeps, fetch_workouts, fetch_cycles,
    fetch_profile, fetch_body_measurement,
    Recovery, Sleep, Workout, Cycle, Profile, BodyMeasurement,
)
```

All collection fetches share the signature
`fetch_*(*, start=None, end=None, max_records=100) -> list[...]` and
**auto-paginate** (Whoop pages at 25/request) up to `max_records`.
`start`/`end` accept a tz-aware `datetime` or an ISO string.

`fetch_profile() -> Profile` and `fetch_body_measurement() ->
BodyMeasurement` are single-object (no pagination).

Dataclass fields worth knowing:

- `Recovery`: `recovery_score` (0-100), `hrv_rmssd_milli`,
  `resting_heart_rate`, `spo2_percentage`, `skin_temp_celsius`,
  `user_calibrating`, `score_state`, `created_at` (tz-aware),
  `cycle_id`, `sleep_id`.
- `Sleep`: `sleep_performance_percentage`,
  `sleep_efficiency_percentage`, `sleep_consistency_percentage`,
  `respiratory_rate`, `nap` (bool), `start`/`end` (tz-aware),
  `stage_summary` (dict), `sleep_needed` (dict).
- `Workout`: `sport_name`, `strain` (0-21), `average_heart_rate`,
  `max_heart_rate`, `kilojoule`, plus a **`calories` property**
  (kJ / 4.184), `distance_meter`, `zone_durations` (dict).
- `Cycle`: `strain`, `kilojoule`, `average_heart_rate`,
  `max_heart_rate`, `start`/`end` (the current cycle has `end=None`).
- `Profile`: `user_id`, `email`, `first_name`, `last_name`.
- `BodyMeasurement`: `height_meter`, `weight_kilogram`, `max_heart_rate`.

## Gotchas

- **Recovery is a morning metric.** No record exists until the preceding
  sleep cycle closes; querying before wake yields nothing for "today".
- **Score fields can be `None`** when `score_state` is `"PENDING_SCORE"`
  or `"UNSCORABLE"`. Always check before formatting.
- **Units are SI/raw**: HRV in milliseconds, distance in meters, energy
  in kilojoules (use `Workout.calories` for kcal), temperature in Celsius.
- **Auto-pagination**: `max_records` is the only knob; the CLI/Python
  layer handles `nextToken` internally.

# Whoop

Read-only access to recovery, sleep, workouts, cycles, profile, and body
measurements from the Whoop v2 API.

| | |
| --- | --- |
| Import | `from mgdio.whoop import fetch_recoveries, fetch_sleeps, fetch_workouts, fetch_cycles, fetch_profile, fetch_body_measurement` |
| Returns | [`Recovery`](../reference/whoop.md), `Sleep`, `Workout`, `Cycle`, `Profile`, `BodyMeasurement` frozen dataclasses |
| CLI | `mgdio whoop recoveries / sleeps / workouts / cycles / profile / body` |
| Reference | [mgdio.whoop](../reference/whoop.md) |
| Example | [`examples/whoop_demo.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/whoop_demo.py) |

## Setup

Whoop uses OAuth 2.0 (authorization-code flow). One-time developer-app setup:

1. Open <https://developer-dashboard.whoop.com> and sign in with your Whoop
   account.
2. Create a **Team**, then an **App**.
3. Set the app's **Redirect URI** to exactly `http://localhost:8765/callback`
   (see the override note below for a different port).
4. Select the scopes `offline read:recovery read:sleep read:workout
   read:cycles read:profile read:body_measurement`. `offline` is required so
   mgdio receives a refresh token.
5. Copy the **Client ID** and **Client Secret**.

Then:

```bash
mgdio auth whoop
```

A setup page opens where you paste the Client ID and Secret (saved to the
keyring under `mgdio:whoop`), click **Authorize with Whoop**, and approve. The
access and refresh token bundle is stored and **refreshed automatically**.

### Headless Whoop auth

On a browserless machine, `mgdio auth whoop --headless` prints the auth URL to
open on any device with a browser and then waits for you to paste the callback
URL back. The best experience pairs it with `--catch`:

1. On the machine with the browser (your laptop), where mgdio is also
   installed, run `mgdio auth whoop --catch`. It serves the callback URI
   locally, never sees your app credentials, and stores nothing.
2. On the headless machine, run `mgdio auth whoop --headless` and open the
   printed URL in the laptop's browser.
3. After you approve, the browser lands on a page that **displays the full
   callback URL** with a copy button (it is printed in the catcher's terminal
   too). Paste it into the waiting `--headless` prompt.

Without `--catch`, the browser lands on a page that fails to load. That is
expected: the URL to paste is in that dead page's address bar and starts with
your registered redirect URI. Bad or empty pastes re-prompt, and the printed
auth URL stays valid.

??? note "The callback URL never appears in the address bar"
    Something on the browser machine is intercepting the redirect, most often
    VS Code's Remote-SSH port auto-forwarding, which forwards any
    `localhost:<port>` URL printed in an integrated terminal and hangs the
    redirect until the one-time code expires. Set
    `"remote.autoForwardPorts": false` to stop it. Alternatively pull the URL
    from the network log: DevTools → Network → tick **Preserve log** → click
    **GRANT** again → find the `auth?client_id=...` request (status 302) and
    copy its `Location` response header. Paste it quickly; the embedded code
    expires within minutes.

??? note "Redirect URI override"
    The callback defaults to `http://localhost:8765/callback`. To use another
    port or path, set `MGDIO_WHOOP_REDIRECT_URI` in your environment or `.env`
    **and** register the same value in your Whoop app. The setup page always
    shows the effective value.

??? note "Stale refresh tokens"
    Whoop rotates refresh tokens on every use and rejects one that has fallen
    out of rotation. A definitive rejection (HTTP 400/401) asks for
    re-authorization; transient failures raise `MgdioAPIError` and leave the
    stored token alone so the next run can retry.

## Python

The data API is read-only and uses SI units: HRV in milliseconds, energy in
kilojoules (`Workout.calories` converts to kcal), distance in meters. All
collection fetches auto-paginate up to `max_records`.

```python
from datetime import datetime, timedelta, timezone

from mgdio.whoop import (
    fetch_body_measurement,
    fetch_cycles,
    fetch_profile,
    fetch_recoveries,
    fetch_sleeps,
    fetch_workouts,
)

me = fetch_profile()
body = fetch_body_measurement()

# Recovery is a MORNING metric: a record appears after the night's sleep
# cycle closes, so "today" may be empty before you wake up.
for r in fetch_recoveries(max_records=7):
    print(r.created_at, r.recovery_score, r.hrv_rmssd_milli, r.resting_heart_rate)

# Sleep, workouts, cycles share the same signature; start/end must be tz-aware.
now = datetime.now(timezone.utc)
recent_sleep = fetch_sleeps(start=now - timedelta(days=7), max_records=25)
for w in fetch_workouts(max_records=10):
    print(w.sport_name, w.strain, w.calories)   # calories = kJ / 4.184
```

## CLI

```bash
mgdio whoop profile
mgdio whoop body
mgdio whoop recoveries --max 7
mgdio whoop sleeps --max 7
mgdio whoop workouts --max 7
mgdio whoop cycles --max 7
# Bounded (tz-aware ISO datetimes):
mgdio whoop sleeps --start "2026-05-01T00:00:00-04:00" \
  --end "2026-05-12T00:00:00-04:00" --max 25
```

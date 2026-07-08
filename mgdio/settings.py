"""Package-wide settings: paths, scopes, keyring identifiers, logging.

Importing this module is idempotent and has these side effects:

* loads ``.env`` (silent if absent),
* ensures :data:`APP_DATA_DIR` and :data:`GOOGLE_DATA_DIR` exist,
* configures root logging once, only if no handlers are present yet
  (so library users keep control of their root logger), and
* selects a usable :mod:`keyring` backend, falling back to a file-based
  store on headless Linux where no OS vault exists
  (see :mod:`mgdio.keyring_backend`).

All paths use :mod:`platformdirs` so the package works without env vars
on Windows, macOS, and Linux.

Provider-specific configuration is namespaced by prefix
(``GOOGLE_*``, ``YNAB_*``, ``TWILIO_*``, ...). Each provider gets its
own subdirectory under :data:`APP_DATA_DIR` for any on-disk artifacts.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import dotenv
import platformdirs

dotenv.load_dotenv()

APP_NAME: str = "mgdio"
APP_DATA_DIR: Path = Path(platformdirs.user_data_dir(APP_NAME))
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_DATA_DIR: Path = APP_DATA_DIR / "google"
GOOGLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
GOOGLE_CLIENT_SECRET_PATH: Path = GOOGLE_DATA_DIR / "client_secret.json"
GOOGLE_KEYRING_USERNAME: str = "oauth_token"

# Google tokens are stored per account ("profile"), one keyring entry per
# slug at service ``mgdio:google:<slug>``. There is no stored "default"
# profile; which profile is the default for a given environment is set
# via the MGDIO_GOOGLE_PROFILE env var (e.g. in a project's .env). The set
# of known profiles is tracked in an on-disk index (keyring has no
# portable list API). See :mod:`mgdio.auth.google._profiles`.
GOOGLE_PROFILE_INDEX_PATH: Path = GOOGLE_DATA_DIR / "profiles.json"
GOOGLE_PROFILE_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")
GOOGLE_PROFILE_ENV_VAR: str = "MGDIO_GOOGLE_PROFILE"
# Pre-profiles releases stored a single token here; kept only so we can
# detect-and-warn about an orphaned legacy token (never auto-migrated).
LEGACY_GOOGLE_KEYRING_SERVICE: str = "mgdio:google"


def google_keyring_service(slug: str) -> str:
    """Return the per-profile keyring service id, ``mgdio:google:<slug>``."""
    return f"mgdio:google:{slug}"


GOOGLE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)

YNAB_KEYRING_SERVICE: str = "mgdio:ynab"
YNAB_KEYRING_USERNAME: str = "personal_access_token"
YNAB_API_BASE: str = "https://api.ynab.com/v1"

# Google Maps Platform uses an API key (NOT the shared Google OAuth
# token). The user pastes a key from the Cloud Console into a localhost
# setup page; it's stored in the keyring under ``mgdio:maps``.
MAPS_KEYRING_SERVICE: str = "mgdio:maps"
MAPS_KEYRING_USERNAME: str = "api_key"
MAPS_API_BASE: str = "https://maps.googleapis.com/maps/api"

WHOOP_DATA_DIR: Path = APP_DATA_DIR / "whoop"
WHOOP_DATA_DIR.mkdir(parents=True, exist_ok=True)
# Two keyring entries under one service: the pasted app credentials
# (needed for token refresh) and the OAuth token bundle.
WHOOP_KEYRING_SERVICE: str = "mgdio:whoop"
WHOOP_KEYRING_USERNAME_APP: str = "app_credentials"
WHOOP_KEYRING_USERNAME_TOKEN: str = "oauth_token"
WHOOP_AUTH_URL: str = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL: str = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE: str = "https://api.prod.whoop.com/developer"
WHOOP_SCOPES: tuple[str, ...] = (
    "offline",  # required to receive a refresh_token
    "read:recovery",
    "read:sleep",
    "read:workout",
    "read:cycles",
    "read:profile",
    "read:body_measurement",
)
# The redirect URI must match exactly what's registered in the user's
# Whoop developer app. Override via env / .env if you registered a
# different port or path. The setup server derives its bind host, port,
# and callback path from this single value.
WHOOP_REDIRECT_URI: str = os.getenv(
    "MGDIO_WHOOP_REDIRECT_URI", "http://localhost:8765/callback"
)

LOG_LEVEL: str = os.getenv("MGDIO_LOG_LEVEL", "INFO")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

# Select a usable keyring backend now, before any auth subpackage reads
# or writes a token. On Windows/macOS this is a no-op; on headless Linux
# it installs a file-based fallback so credential storage works without
# a Secret Service daemon. Import locally to keep settings' top-level
# import list focused on configuration.
from mgdio.keyring_backend import ensure_keyring_backend  # noqa: E402

ensure_keyring_backend()

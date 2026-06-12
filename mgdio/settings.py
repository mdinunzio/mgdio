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
GOOGLE_KEYRING_SERVICE: str = "mgdio:google"
GOOGLE_KEYRING_USERNAME: str = "oauth_token"
GOOGLE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)

YNAB_KEYRING_SERVICE: str = "mgdio:ynab"
YNAB_KEYRING_USERNAME: str = "personal_access_token"
YNAB_API_BASE: str = "https://api.ynab.com/v1"

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

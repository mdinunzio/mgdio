"""Package-wide settings: paths, scopes, vault keys, logging.

Importing this module is idempotent and has these side effects:

* loads ``.env`` (silent if absent) -- this is also how a project-local
  ``MGDVAULT_PASSWORD`` reaches :mod:`mgdvault`, which reads the
  environment lazily on first use and never loads ``.env`` itself,
* ensures :data:`APP_DATA_DIR` and :data:`GOOGLE_DATA_DIR` exist, and
* configures root logging once, only if no handlers are present yet
  (so library users keep control of their root logger).

All paths use :mod:`platformdirs` so the package works without env vars
on Windows, macOS, and Linux.

Secrets (OAuth tokens, API keys) are **not** kept under
:data:`APP_DATA_DIR`. They live in the shared `mgdvault
<https://github.com/mdinunzio/mgdvault>`_ credential vault under the
``mgdio/`` namespace; the ``*_VAULT_KEY`` constants below name every
secret mgdio reads or writes. Only non-secret artifacts (the Google
OAuth ``client_secret.json``) stay on disk.

Provider-specific configuration is namespaced by prefix
(``GOOGLE_*``, ``YNAB_*``, ``WHOOP_*``, ...).
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

# Every mgdio secret lives under this mgdvault key namespace so one vault
# can be shared with other packages on the machine without collisions.
VAULT_NAMESPACE: str = "mgdio"

GOOGLE_DATA_DIR: Path = APP_DATA_DIR / "google"
GOOGLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
GOOGLE_CLIENT_SECRET_PATH: Path = GOOGLE_DATA_DIR / "client_secret.json"

# Google tokens are stored per account ("profile"), one vault entry per
# slug at ``mgdio/google/<slug>``. There is no stored "default" profile;
# which profile is the default for a given environment is set via the
# MGDIO_GOOGLE_PROFILE env var (e.g. in a project's .env). The set of
# known profiles is simply the keys under :data:`GOOGLE_VAULT_PREFIX`.
GOOGLE_VAULT_PREFIX: str = f"{VAULT_NAMESPACE}/google"
GOOGLE_PROFILE_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")
GOOGLE_PROFILE_ENV_VAR: str = "MGDIO_GOOGLE_PROFILE"


def google_vault_key(slug: str) -> str:
    """Return the per-profile vault key, ``mgdio/google/<slug>``."""
    return f"{GOOGLE_VAULT_PREFIX}/{slug}"


GOOGLE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)

YNAB_VAULT_KEY: str = f"{VAULT_NAMESPACE}/ynab/token"
YNAB_API_BASE: str = "https://api.ynab.com/v1"

# Google Maps Platform uses an API key (NOT the shared Google OAuth
# token). The user pastes a key from the Cloud Console into a localhost
# setup page; it's stored in the vault under ``mgdio/maps/api_key``.
MAPS_VAULT_KEY: str = f"{VAULT_NAMESPACE}/maps/api_key"
MAPS_API_BASE: str = "https://maps.googleapis.com/maps/api"

WHOOP_DATA_DIR: Path = APP_DATA_DIR / "whoop"
WHOOP_DATA_DIR.mkdir(parents=True, exist_ok=True)
# Two vault entries: the pasted app credentials (needed for token
# refresh) and the OAuth token bundle.
WHOOP_VAULT_KEY_APP: str = f"{VAULT_NAMESPACE}/whoop/app_credentials"
WHOOP_VAULT_KEY_TOKEN: str = f"{VAULT_NAMESPACE}/whoop/oauth_token"
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

# --- Pre-mgdvault (<= 0.5) storage, read only by ``mgdio auth migrate-keyring``.
# Secrets used to live in the OS keyring at these service/username pairs,
# with Google profile slugs tracked in an on-disk index file.
LEGACY_GOOGLE_PROFILE_INDEX_PATH: Path = GOOGLE_DATA_DIR / "profiles.json"
LEGACY_KEYRING_GOOGLE_USERNAME: str = "oauth_token"
LEGACY_KEYRING_YNAB: tuple[str, str] = ("mgdio:ynab", "personal_access_token")
LEGACY_KEYRING_MAPS: tuple[str, str] = ("mgdio:maps", "api_key")
LEGACY_KEYRING_WHOOP_APP: tuple[str, str] = ("mgdio:whoop", "app_credentials")
LEGACY_KEYRING_WHOOP_TOKEN: tuple[str, str] = ("mgdio:whoop", "oauth_token")


def legacy_google_keyring_service(slug: str) -> str:
    """Return the pre-mgdvault keyring service id, ``mgdio:google:<slug>``."""
    return f"mgdio:google:{slug}"


LOG_LEVEL: str = os.getenv("MGDIO_LOG_LEVEL", "INFO")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

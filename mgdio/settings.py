"""Package-wide settings: paths, scopes, keyring identifiers, logging.

Importing this module is idempotent and has these side effects:

* loads ``.env`` (silent if absent),
* ensures :data:`APP_DATA_DIR` and :data:`GOOGLE_DATA_DIR` exist, and
* configures root logging once, only if no handlers are present yet
  (so library users keep control of their root logger).

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
)

LOG_LEVEL: str = os.getenv("MGDIO_LOG_LEVEL", "INFO")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

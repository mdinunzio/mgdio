"""Package-wide settings: paths, scopes, keyring identifiers, logging.

Importing this module is idempotent and has three side effects:

* loads ``.env`` (silent if absent),
* ensures :data:`APP_DATA_DIR` exists, and
* configures root logging once, only if no handlers are present yet
  (so library users keep control of their root logger).

All paths use :mod:`platformdirs` so the package works without env vars
on Windows, macOS, and Linux.
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

GMAIL_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/gmail.modify",)
GMAIL_CLIENT_SECRET_PATH: Path = APP_DATA_DIR / "client_secret.json"

KEYRING_SERVICE_GMAIL: str = "mgdio:gmail"
KEYRING_USERNAME_GMAIL: str = "oauth_token"

LOG_LEVEL: str = os.getenv("MGDIO_LOG_LEVEL", "INFO")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

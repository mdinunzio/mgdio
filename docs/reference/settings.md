# mgdio.settings { #mgdio.settings }

Constants are shown with their default values. Environment variables read at
import time: `MGDIO_GOOGLE_PROFILE`, `MGDIO_WHOOP_REDIRECT_URI`,
`MGDIO_LOG_LEVEL`, `MGDIO_NONINTERACTIVE`, `MGDIO_KEYRING_PLAINTEXT`,
`MGDIO_KEYRING_BACKEND` (and the standard `PYTHON_KEYRING_BACKEND`). A `.env`
file in the working directory is loaded first.

::: mgdio.settings
    options:
      show_if_no_docstring: true

## mgdio.keyring_backend { #mgdio.keyring_backend }

Imported by `mgdio.settings` so that a usable keyring backend is selected
before any provider touches the vault. See
[Linux keyring fallback](../auth.md#linux-keyring-fallback) for the
user-facing behavior.

::: mgdio.keyring_backend
    options:
      heading_level: 3

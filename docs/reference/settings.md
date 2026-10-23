# mgdio.settings { #mgdio.settings }

Constants are shown with their default values. Environment variables read at
import time: `MGDIO_GOOGLE_PROFILE`, `MGDIO_WHOOP_REDIRECT_URI`,
`MGDIO_LOG_LEVEL`, `MGDIO_NONINTERACTIVE`. A `.env` file in the working
directory is loaded first, which is also how a project-local
`MGDVAULT_PASSWORD` reaches [mgdvault](https://github.com/mdinunzio/mgdvault);
see [Credential vault](../auth.md#credential-vault) for the `MGDVAULT_*`
variables.

::: mgdio.settings
    options:
      show_if_no_docstring: true

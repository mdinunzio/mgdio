"""Authentication subsystem for mgdio.

Each external provider that mgdio talks to is a subpackage under
``mgdio.auth`` exposing a uniform public surface:

* ``get_credentials()`` -- returns a provider-specific credentials object,
  running first-time setup automatically if needed.
* ``clear_stored_token()`` -- wipes any cached secrets for the provider.
* ``reset_credentials_cache()`` -- clears the in-process cache (test/diagnostic).

Currently implemented: :mod:`mgdio.auth.google` (multi-account),
:mod:`mgdio.auth.ynab`, :mod:`mgdio.auth.whoop`, :mod:`mgdio.auth.maps`.

:func:`mgdio.auth.status.get_auth_status` aggregates which providers are
set up on this machine (surfaced by ``mgdio auth status``).

Planned: ``mgdio.auth.twilio``.
"""

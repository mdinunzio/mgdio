"""Authentication subsystem for mgdio.

Each external provider that mgdio talks to is a subpackage under
``mgdio.auth`` exposing a uniform public surface:

* ``get_credentials()`` -- returns a provider-specific credentials object,
  running first-time setup automatically if needed.
* ``clear_stored_token()`` -- wipes any cached secrets for the provider.
* ``reset_credentials_cache()`` -- clears the in-process cache (test/diagnostic).

Currently implemented: :mod:`mgdio.auth.google`.

Planned: ``mgdio.auth.ynab``, ``mgdio.auth.twilio``.
"""

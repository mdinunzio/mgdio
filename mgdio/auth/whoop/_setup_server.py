"""Localhost setup server for one-shot Whoop OAuth onboarding.

When the user runs ``mgdio auth whoop`` and there's no usable token,
this module starts a tiny HTTP server bound to the host + port of
:data:`mgdio.settings.WHOOP_REDIRECT_URI`, opens the browser at ``/``,
and walks the user through:

1. Reading instructions for creating a Whoop developer app and copying
   its Client ID + Secret.
2. Pasting both into the form; they're saved to the OS keyring
   (``mgdio:whoop`` / ``app_credentials``).
3. Clicking "Authorize with Whoop", which opens Whoop's consent screen
   in a new tab. After the user approves, Whoop redirects back to the
   callback path on this same local server with an authorization code.
4. The callback handler exchanges the code for an access+refresh token
   bundle, validates it against ``/v2/user/profile/basic``, and returns
   it to the caller for keyring storage.

The bind host, port, and callback path are all derived from
``WHOOP_REDIRECT_URI`` so they always agree with what the user
registered in their Whoop app. Override the URI via
``MGDIO_WHOOP_REDIRECT_URI`` (env or ``.env``).
"""

from __future__ import annotations

import html
import json
import logging
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import keyring
import requests

from mgdio.auth import _keyring
from mgdio.exceptions import MgdioAuthError
from mgdio.settings import (
    WHOOP_API_BASE,
    WHOOP_AUTH_URL,
    WHOOP_KEYRING_SERVICE,
    WHOOP_KEYRING_USERNAME_APP,
    WHOOP_REDIRECT_URI,
    WHOOP_SCOPES,
    WHOOP_TOKEN_URL,
)

logger = logging.getLogger(__name__)

# Derive the local listener + callback path from the (env-overridable)
# redirect URI so changing one moves both in lockstep.
_PARSED = urlparse(WHOOP_REDIRECT_URI)
_BIND_HOST = _PARSED.hostname or "localhost"
_BIND_PORT = _PARSED.port or 80
_CALLBACK_PATH = _PARSED.path or "/callback"


class SetupResult:
    """Holds the outcome of the setup flow, populated by the request handler.

    Attributes:
        token: Token bundle dict on success, else ``None``.
        error: Last error message, else ``None``.
        state: Random CSRF token tying the auth request to the callback.
        done_event: Set once the flow reaches a terminal state.
    """

    def __init__(self) -> None:
        """Initialize an empty result with a fresh state token."""
        self.token: dict | None = None
        self.error: str | None = None
        self.state: str = secrets.token_urlsafe(24)
        self.done_event = threading.Event()


def run_setup_flow() -> dict:
    """Run the browser-based onboarding flow and return a token bundle.

    Returns:
        A token bundle dict: ``{access_token, refresh_token, expires_at,
        scope, token_type}``.

    Raises:
        MgdioAuthError: If the bind port is in use, or the user cancels,
            or the code exchange / validation fails.
    """
    result = SetupResult()
    handler_class = _make_handler_class(result)

    try:
        server = ThreadingHTTPServer((_BIND_HOST, _BIND_PORT), handler_class)
    except OSError as exc:
        raise MgdioAuthError(
            f"Could not bind {_BIND_HOST}:{_BIND_PORT} for the Whoop callback "
            f"({exc}). Free that port, or set MGDIO_WHOOP_REDIRECT_URI to a "
            f"different host/port (and update your Whoop app to match)."
        ) from exc

    server_thread = threading.Thread(
        target=server.serve_forever, name="mgdio-whoop-setup-server", daemon=True
    )
    server_thread.start()

    url = f"http://{_BIND_HOST}:{_BIND_PORT}/"
    logger.info("Opening Whoop setup page at %s", url)
    webbrowser.open(url)

    try:
        result.done_event.wait()
    finally:
        time.sleep(0.5)
        server.shutdown()
        server.server_close()

    if result.token is None:
        raise MgdioAuthError(result.error or "Whoop setup flow did not complete.")
    return result.token


def run_headless_flow() -> dict:
    """Copy-paste OAuth flow for machines without a browser.

    Same contract as :func:`run_setup_flow`, but nothing listens locally:
    we print the authorization URL, the user opens it on a device that
    *does* have a browser, and after consent their browser is redirected
    to the registered ``localhost`` callback -- which fails to load on
    *their* machine. That's expected: they copy the full failed-redirect
    URL from the address bar and paste it back into this terminal, and we
    parse the code out of it.

    If app credentials (Client ID / Secret) aren't stored yet, they're
    prompted for on the terminal first and saved to the keyring.

    A bad paste (empty, wrong state, no code) re-prompts up to
    ``_MAX_PASTE_ATTEMPTS`` times with a specific hint rather than
    aborting -- the ``state`` is minted once per run, so the auth URL
    printed above stays valid across retries.

    Returns:
        A token bundle dict: ``{access_token, refresh_token, expires_at,
        scope, token_type}``.

    Raises:
        MgdioAuthError: If no usable URL is pasted after all attempts,
            or the exchange/validation fails.
    """
    app = _load_app_credentials_or_empty()
    if not app.get("client_id") or not app.get("client_secret"):
        _prompt_and_save_app_credentials()

    state = secrets.token_urlsafe(24)
    _print_headless_instructions(_build_authorization_url(state))
    code = _prompt_for_code(state)
    token = _exchange_code(code)
    ok, message = _validate_access_token(token["access_token"])
    if not ok:
        raise MgdioAuthError(f"Whoop token validation failed: {message}")
    # Confirm WHICH account was authorized (e.g. "Authorized as Jane Doe
    # (jane@x.com).") so a wrong-account consent is caught immediately.
    print(message, file=sys.stderr, flush=True)
    return token


# Bad pastes re-prompt (the state survives retries); aborting instead would
# mint a new state on the re-run, invalidating a consent the user already
# completed and compounding the confusion.
_MAX_PASTE_ATTEMPTS = 3

_PASTE_PROMPT = "paste the FULL address-bar URL from the failed/blank page > "


def run_catch_server() -> None:
    """Serve the OAuth callback locally and display the URL to paste.

    The ``--catch`` companion to :func:`run_headless_flow`: run this on
    the machine WITH the browser while the headless prompt waits on the
    other machine. It binds the redirect URI's host/port, so the
    post-consent redirect lands on a real page showing the full
    callback URL to paste -- no dead page, no address-bar spelunking,
    and immune to port-forward hangs (the design stops depending on the
    redirect *failing* and serves it instead).

    Nothing is exchanged or stored here: the catcher never sees app
    credentials, only relays the redirect URL. Runs until Ctrl-C so a
    re-consent after an expired code is caught too.

    Raises:
        MgdioAuthError: If the redirect URI's port can't be bound.
    """
    server = _make_catch_server()
    print(
        f"\n=== mgdio Whoop callback catcher ===\n\n"
        f"Listening at {WHOOP_REDIRECT_URI}\n\n"
        f"1. On the OTHER machine, run `mgdio auth whoop --headless`.\n"
        f"2. Open the auth URL it prints in a browser on THIS machine.\n"
        f"3. Approve -- the post-consent page here will show the full\n"
        f"   callback URL (also printed below). Paste it into the\n"
        f"   waiting prompt quickly; its code expires within minutes.\n\n"
        f"Press Ctrl-C to stop.\n",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr, flush=True)
    finally:
        server.server_close()


def _make_catch_server() -> ThreadingHTTPServer:
    """Bind the redirect URI's host/port with the catch handler.

    Raises:
        MgdioAuthError: If the port is taken (names the usual suspects).
    """
    try:
        return ThreadingHTTPServer(
            (_BIND_HOST, _BIND_PORT), _make_catch_handler_class()
        )
    except OSError as exc:
        raise MgdioAuthError(
            f"Could not bind {_BIND_HOST}:{_BIND_PORT} for the catcher "
            f"({exc}). Something already holds that port -- VS Code "
            f"port-forwarding is a common culprit "
            f"(`lsof -nP -i :{_BIND_PORT}` names it). Free the port, or "
            f"set MGDIO_WHOOP_REDIRECT_URI to a different host/port (and "
            f"update your Whoop app to match)."
        ) from exc


def _make_catch_handler_class():
    """Request handler that echoes the callback URL instead of using it."""

    class _CatchHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            logger.debug(
                "whoop-catch-server %s - %s", self.address_string(), format % args
            )

        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path != _CALLBACK_PATH:
                self.send_error(404)
                return
            url = f"http://{_BIND_HOST}:{_BIND_PORT}{self.path}"
            print(
                f"\nCaught callback -- paste this into the waiting prompt:\n\n"
                f"{url}\n",
                file=sys.stderr,
                flush=True,
            )
            body = _render_caught(url).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _CatchHandler


def _render_caught(url: str) -> str:
    return _CAUGHT_TEMPLATE.format(url=html.escape(url, quote=True))


def _read_line(prompt: str) -> str:
    """``input()`` that turns a closed stdin into an actionable error.

    Raises:
        MgdioAuthError: On EOF -- e.g. the command was run without a
            usable stdin (piped, orphaned session).
    """
    try:
        return input(prompt)
    except EOFError as exc:
        raise MgdioAuthError(
            "stdin closed before input was provided -- run this command in "
            "an interactive terminal."
        ) from exc


def _prompt_for_code(state: str) -> str:
    """Read pastes from stdin until one yields an auth code (or give up).

    Raises:
        MgdioAuthError: After ``_MAX_PASTE_ATTEMPTS`` unusable pastes
            (the last parse error propagates when there was input), or
            immediately if stdin is closed.
    """
    for attempts_left in range(_MAX_PASTE_ATTEMPTS - 1, -1, -1):
        pasted = _read_line(_PASTE_PROMPT)
        if not pasted.strip():
            if attempts_left == 0:
                break
            _print_reprompt_hint("Nothing pasted.", attempts_left)
            continue
        try:
            return _parse_redirect_url(pasted, state)
        except MgdioAuthError as exc:
            if attempts_left == 0:
                raise
            _print_reprompt_hint(str(exc), attempts_left)
    raise MgdioAuthError(
        f"No redirect URL pasted after {_MAX_PASTE_ATTEMPTS} attempts; aborting."
    )


def _print_reprompt_hint(problem: str, attempts_left: int) -> None:
    print(
        f"\n{problem}\n{attempts_left} attempt(s) left -- the auth URL "
        "printed above is still valid.",
        file=sys.stderr,
        flush=True,
    )


def _parse_redirect_url(pasted: str, expected_state: str) -> str:
    """Extract the authorization code from a pasted redirect URL.

    Tolerant of real-world paste shapes: whitespace and line-wraps that
    terminal copying introduces are collapsed, and a bare query fragment
    (``code=...&state=...``, or just ``code=...``) is accepted alongside
    a full URL. A missing ``state`` is allowed with a warning (a
    hand-trimmed paste); a *wrong* one is still rejected.

    Raises:
        MgdioAuthError: If Whoop reported an error, the state doesn't
            match this session, or no code is present.
    """
    cleaned = "".join(pasted.split())
    query = urlparse(cleaned).query
    if not query and "=" in cleaned and "://" not in cleaned:
        query = cleaned.lstrip("?")
    params = parse_qs(query)
    if params.get("error"):
        raise MgdioAuthError(f"Whoop returned an error: {params['error'][0]}")
    state = (params.get("state") or [""])[0]
    if state and state != expected_state:
        raise MgdioAuthError(
            "State mismatch: that URL is from an earlier attempt or "
            "session. Redo the consent from the auth URL printed above, "
            "then paste the fresh address-bar URL."
        )
    code = (params.get("code") or [""])[0]
    if not code:
        raise MgdioAuthError(
            "No authorization code found. Copy the FULL address-bar URL "
            "from the failed/blank post-consent page (it contains "
            "'code=...')."
        )
    if not state:
        logger.warning(
            "Pasted value had no 'state' parameter; proceeding with the " "code alone."
        )
    return code


def _prompt_and_save_app_credentials() -> None:
    """Prompt for the Whoop app's Client ID / Secret and save them.

    Raises:
        MgdioAuthError: If either value is left empty.
    """
    msg = (
        "\nNo Whoop app credentials stored. Create an app at\n"
        "https://developer.whoop.com (Dashboard -> Create app) with\n"
        f"redirect URI exactly: {WHOOP_REDIRECT_URI}\n"
        "then paste its credentials below.\n"
    )
    print(msg, file=sys.stderr, flush=True)
    client_id = _read_line("Client ID > ").strip()
    client_secret = _read_line("Client Secret > ").strip()
    if not client_id or not client_secret:
        raise MgdioAuthError("Client ID and Secret are both required; aborting.")
    _save_app_credentials(client_id, client_secret)


def _print_headless_instructions(auth_url: str) -> None:
    """Print the copy-paste steps + auth URL to stderr, warning FIRST.

    The dead-page warning deliberately comes *before* the auth URL:
    users open the URL the moment they see it and never read past it,
    then mistake the failed post-consent page for breakage.
    """
    msg = (
        "\n=== mgdio headless Whoop auth ===\n\n"
        "READ THIS FIRST: after you approve, your browser lands on a page\n"
        "that FAILS to load or renders BLANK. That is EXPECTED -- the\n"
        "address bar of that dead page holds the URL you paste back here.\n"
        "It starts with:\n\n"
        f"   {WHOOP_REDIRECT_URI}?...\n\n"
        "(the redirect URI registered in your Whoop app -- the default\n"
        "unless you set MGDIO_WHOOP_REDIRECT_URI).\n\n"
        "1. On a machine WITH a browser, open this URL:\n\n"
        f"   {auth_url}\n\n"
        "2. Sign in to Whoop and approve the requested access.\n"
        "3. Copy the FULL address-bar URL from the failed/blank page.\n"
        "4. Paste it below and press Enter.\n\n"
        "Tip: if mgdio is installed on the browser machine, run\n"
        "`mgdio auth whoop --catch` there FIRST -- the post-consent page\n"
        "then displays the URL to paste instead of failing to load.\n\n"
        "Troubleshooting -- approved, but the address bar never shows the\n"
        "callback URL (or takes minutes)? Something on that machine is\n"
        "intercepting the redirect (VS Code port-forwarding is a common\n"
        "culprit). Grab the URL from the browser's network log instead:\n\n"
        "  a. On the consent tab, open DevTools (F12 / Cmd+Option+I),\n"
        "     select the Network panel, and tick 'Preserve log'.\n"
        "  b. Click GRANT again.\n"
        "  c. Find the 'auth?client_id=...' request (status 302). Its\n"
        "     'Location' response header is the full callback URL --\n"
        "     copy it and paste it below. Move quickly: the code in\n"
        "     that URL expires within minutes.\n"
    )
    # stderr so stdout stays clean for callers that might pipe output.
    print(msg, file=sys.stderr, flush=True)


def _build_authorization_url(state: str) -> str:
    """Build the Whoop OAuth authorization URL."""
    params = {
        "client_id": _load_app_credentials_or_empty().get("client_id", ""),
        "response_type": "code",
        "redirect_uri": WHOOP_REDIRECT_URI,
        "scope": " ".join(WHOOP_SCOPES),
        "state": state,
    }
    return f"{WHOOP_AUTH_URL}?{urlencode(params)}"


def _exchange_code(code: str) -> dict:
    """Exchange an authorization code for a token bundle.

    Raises:
        MgdioAuthError: On transport error, non-200, or non-JSON response.
    """
    app = _load_app_credentials_or_empty()
    try:
        resp = requests.post(
            WHOOP_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": WHOOP_REDIRECT_URI,
                "client_id": app.get("client_id", ""),
                "client_secret": app.get("client_secret", ""),
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise MgdioAuthError(f"Whoop token exchange transport error: {exc}") from exc

    if resp.status_code != 200:
        raise MgdioAuthError(
            f"Whoop token exchange failed (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise MgdioAuthError("Whoop token exchange returned non-JSON body") from exc

    expires_in = int(payload.get("expires_in", 3600))
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "expires_at": time.time() + expires_in - 60,
        "scope": payload.get("scope", ""),
        "token_type": payload.get("token_type", "bearer"),
    }


def _validate_access_token(access_token: str) -> tuple[bool, str]:
    """Hit ``/v2/user/profile/basic`` to confirm the new token works."""
    try:
        resp = requests.get(
            f"{WHOOP_API_BASE}/v2/user/profile/basic",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach Whoop: {exc}"
    if resp.status_code == 200:
        return True, _authorized_message(resp)
    if resp.status_code == 401:
        return False, "Whoop rejected the access token (401)."
    return False, f"Whoop returned HTTP {resp.status_code}: {resp.text[:200]}"


def _authorized_message(resp: requests.Response) -> str:
    """``"Authorized as First Last (email)."`` when the profile body allows.

    Naming the verified account confirms the *right* one was authorized
    without a follow-up ``mgdio whoop profile``.
    """
    try:
        profile = resp.json()
    except ValueError:
        return "Authorized."
    if not isinstance(profile, dict):
        return "Authorized."
    name = " ".join(
        part
        for part in [profile.get("first_name", ""), profile.get("last_name", "")]
        if part
    )
    email = profile.get("email", "")
    who = f"{name} ({email})" if name and email else name or email
    return f"Authorized as {who}." if who else "Authorized."


def _save_app_credentials(client_id: str, client_secret: str) -> None:
    _keyring.set_password(
        WHOOP_KEYRING_SERVICE,
        WHOOP_KEYRING_USERNAME_APP,
        json.dumps({"client_id": client_id, "client_secret": client_secret}),
    )


def _load_app_credentials_or_empty() -> dict:
    raw = keyring.get_password(WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_APP)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _make_handler_class(result: SetupResult):
    """Build a request handler class closed over the setup state."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            logger.debug(
                "whoop-setup-server %s - %s", self.address_string(), format % args
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/" or self.path.startswith("/?"):
                self._send_html(_render_page())
            elif parsed.path == _CALLBACK_PATH:
                self._handle_callback(parse_qs(parsed.query))
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/credentials":
                self._handle_credentials()
            elif self.path == "/authorize":
                self._handle_authorize()
            elif self.path == "/cancel":
                self._handle_cancel()
            else:
                self.send_error(404)

        def _send_html(self, body: str, status: int = 200) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, data: dict, status: int = 200) -> None:
            payload = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _read_json_body(self) -> dict | None:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8_000:
                self._send_json(
                    {"ok": False, "message": "Empty or oversized payload."},
                    status=400,
                )
                return None
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send_json(
                    {"ok": False, "message": f"Not valid JSON: {exc}"},
                    status=400,
                )
                return None

        def _handle_credentials(self) -> None:
            parsed = self._read_json_body()
            if parsed is None:
                return
            client_id = (parsed.get("client_id") or "").strip()
            client_secret = (parsed.get("client_secret") or "").strip()
            if not client_id or not client_secret:
                self._send_json(
                    {
                        "ok": False,
                        "message": "Both Client ID and Client Secret are required.",
                    },
                    status=400,
                )
                return
            _save_app_credentials(client_id, client_secret)
            self._send_json({"ok": True, "message": "Credentials saved."})

        def _handle_authorize(self) -> None:
            app = _load_app_credentials_or_empty()
            if not app.get("client_id"):
                self._send_json(
                    {"ok": False, "message": "Save your Client ID / Secret first."},
                    status=400,
                )
                return
            self._send_json(
                {"ok": True, "auth_url": _build_authorization_url(result.state)}
            )

        def _handle_callback(self, query: dict) -> None:
            error = query.get("error", [None])[0]
            if error:
                result.error = f"Whoop authorization denied: {error}"
                self._send_html(_render_done(False, result.error))
                result.done_event.set()
                return

            state = query.get("state", [None])[0]
            code = query.get("code", [None])[0]
            if state != result.state:
                result.error = "State mismatch on Whoop callback (possible CSRF)."
                self._send_html(_render_done(False, result.error))
                result.done_event.set()
                return
            if not code:
                result.error = "Whoop callback missing authorization code."
                self._send_html(_render_done(False, result.error))
                result.done_event.set()
                return

            try:
                bundle = _exchange_code(code)
            except MgdioAuthError as exc:
                result.error = str(exc)
                self._send_html(_render_done(False, result.error))
                result.done_event.set()
                return

            ok, message = _validate_access_token(bundle["access_token"])
            if not ok:
                result.error = message
                self._send_html(_render_done(False, message))
                result.done_event.set()
                return

            result.token = bundle
            self._send_html(_render_done(True, f"{message} You can close this tab."))
            result.done_event.set()

        def _handle_cancel(self) -> None:
            self._send_json({"ok": True})
            if result.token is None:
                result.error = result.error or "Cancelled by user."
            result.done_event.set()

    return _Handler


def _render_page() -> str:
    return _PAGE_TEMPLATE.format(
        redirect_uri=WHOOP_REDIRECT_URI,
        scopes=" ".join(WHOOP_SCOPES),
    )


def _render_done(ok: bool, message: str) -> str:
    cls = "ok" if ok else "err"
    icon = "✅" if ok else "⚠️"
    return _DONE_TEMPLATE.format(cls=cls, icon=icon, message=message)


_PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - Whoop setup</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 760px; margin: 2.5rem auto; padding: 0 1.25rem;
    line-height: 1.55;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
  code, pre {{
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    background: rgba(127,127,127,0.12); padding: 0.1rem 0.35rem;
    border-radius: 4px;
  }}
  ol li {{ margin: 0.4rem 0; }}
  a {{ color: #2563eb; }}
  label {{ display: block; margin-top: 0.85rem; font-weight: 600; }}
  input {{
    width: 100%; box-sizing: border-box; padding: 0.55rem 0.75rem;
    margin-top: 0.25rem; border: 1px solid #888; border-radius: 6px;
    font: inherit;
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  }}
  button {{
    font: inherit; padding: 0.6rem 1.1rem; border-radius: 6px;
    border: 1px solid #2563eb; background: #2563eb; color: white;
    cursor: pointer;
  }}
  button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  #status {{ margin-top: 1rem; min-height: 1.4rem; }}
  .ok {{ color: #16a34a; }}
  .err {{ color: #dc2626; }}
  .note {{
    border-left: 4px solid #d97706; padding: 0.5rem 0.85rem;
    background: rgba(217,119,6,0.08); margin: 1rem 0; border-radius: 4px;
  }}
</style>
</head>
<body>
<h1>mgdio - Whoop setup</h1>
<p>
  One-time setup to authorize <strong>mgdio</strong> against your Whoop
  account. This page is served from your own machine.
</p>

<h2>1. Create a Whoop developer app</h2>
<ol>
  <li>Open
      <a href="https://developer-dashboard.whoop.com/" target="_blank">
      developer-dashboard.whoop.com</a> and sign in with your Whoop
      account.</li>
  <li>Create a <strong>Team</strong>, then create a new <strong>App</strong>.</li>
  <li>Set the app's <strong>Redirect URI</strong> to exactly:<br>
      <code>{redirect_uri}</code></li>
  <li>Select these <strong>Scopes</strong>:<br>
      <code>{scopes}</code></li>
  <li>Save, then copy the <strong>Client ID</strong> and
      <strong>Client Secret</strong>.</li>
</ol>

<h2>2. Paste your Client ID + Secret</h2>
<label for="client_id">Client ID</label>
<input id="client_id" spellcheck="false" autocomplete="off"
       placeholder="paste your Whoop Client ID">
<label for="client_secret">Client Secret</label>
<input id="client_secret" type="password" spellcheck="false" autocomplete="off"
       placeholder="paste your Whoop Client Secret">
<p style="margin-top:1rem">
  <button id="save">Save credentials</button>
  <button id="authorize" disabled
          style="margin-left:0.5rem">Authorize with Whoop</button>
  <button id="cancel" style="background:#6b7280;border-color:#6b7280;
          margin-left:0.5rem">Cancel</button>
</p>
<p id="status"></p>

<div class="note">
  Credentials are stored in your OS credential vault (Windows Credential
  Manager / macOS Keychain / Linux Secret Service) under
  <code>mgdio:whoop</code>. The redirect URI defaults to
  <code>{redirect_uri}</code> &mdash; change it by setting
  <code>MGDIO_WHOOP_REDIRECT_URI</code> in your environment or
  <code>.env</code> (and updating your Whoop app to match).
</div>

<script>
const idEl = document.getElementById('client_id');
const secretEl = document.getElementById('client_secret');
const saveBtn = document.getElementById('save');
const authBtn = document.getElementById('authorize');
const cancelBtn = document.getElementById('cancel');
const statusEl = document.getElementById('status');

function setStatus(text, cls) {{
  statusEl.textContent = text;
  statusEl.className = cls || '';
}}

saveBtn.addEventListener('click', async () => {{
  const clientId = idEl.value.trim();
  const clientSecret = secretEl.value.trim();
  if (!clientId || !clientSecret) {{
    setStatus('Enter both Client ID and Client Secret.', 'err');
    return;
  }}
  saveBtn.disabled = true;
  setStatus('Saving...');
  try {{
    const r = await fetch('/credentials', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{client_id: clientId, client_secret: clientSecret}}),
    }});
    const data = await r.json();
    if (data.ok) {{
      setStatus('Saved. Now click "Authorize with Whoop".', 'ok');
      authBtn.disabled = false;
    }} else {{
      setStatus(data.message || 'Save failed.', 'err');
      saveBtn.disabled = false;
    }}
  }} catch (err) {{
    setStatus('Save failed: ' + err, 'err');
    saveBtn.disabled = false;
  }}
}});

authBtn.addEventListener('click', async () => {{
  authBtn.disabled = true;
  setStatus('Opening Whoop consent screen...');
  try {{
    const r = await fetch('/authorize', {{method: 'POST'}});
    const data = await r.json();
    if (data.ok) {{
      setStatus('Approve access in the new tab, then return here.', 'ok');
      window.open(data.auth_url, '_blank');
    }} else {{
      setStatus(data.message || 'Could not start authorization.', 'err');
      authBtn.disabled = false;
    }}
  }} catch (err) {{
    setStatus('Authorization failed: ' + err, 'err');
    authBtn.disabled = false;
  }}
}});

cancelBtn.addEventListener('click', async () => {{
  await fetch('/cancel', {{method: 'POST'}});
  setStatus('Cancelled. You can close this tab.', 'err');
  saveBtn.disabled = true;
  authBtn.disabled = true;
  cancelBtn.disabled = true;
}});

idEl.focus();
</script>

</body>
</html>
"""


_DONE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - Whoop setup</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 640px; margin: 4rem auto; padding: 0 1.25rem; text-align: center;
  }}
  .ok {{ color: #16a34a; }}
  .err {{ color: #dc2626; }}
  .icon {{ font-size: 3rem; }}
</style>
</head>
<body>
<div class="icon">{icon}</div>
<h1 class="{cls}">{message}</h1>
<p>Return to your terminal.</p>
</body>
</html>
"""

_CAUGHT_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - Whoop callback caught</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 760px; margin: 4rem auto; padding: 0 1.25rem;
    text-align: center; line-height: 1.55;
  }}
  .icon {{ font-size: 3rem; }}
  h1 {{ color: #16a34a; font-size: 1.6rem; }}
  code {{
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    background: rgba(127,127,127,0.12); padding: 0.1rem 0.35rem;
    border-radius: 4px;
  }}
  textarea {{
    width: 100%; min-height: 7rem; margin-top: 1rem; padding: 0.6rem;
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    font-size: 0.85rem; border-radius: 8px; box-sizing: border-box;
  }}
  button {{
    margin-top: 0.75rem; padding: 0.55rem 1.4rem; font-size: 1rem;
    border-radius: 8px; cursor: pointer;
  }}
  .hint {{ opacity: 0.7; font-size: 0.9rem; margin-top: 1rem; }}
</style>
</head>
<body>
<div class="icon">&#x1F3AF;</div>
<h1>Callback caught</h1>
<p>Paste this into the waiting <code>mgdio auth whoop --headless</code>
prompt on the other machine:</p>
<textarea readonly onclick="this.select()">{url}</textarea>
<div><button onclick="
  navigator.clipboard.writeText(document.querySelector('textarea').value)
    .then(() => this.textContent = 'Copied!');
">Copy to clipboard</button></div>
<p class="hint">Move quickly &mdash; the code in this URL expires within
minutes. The URL was also printed in the catcher's terminal.</p>
</body>
</html>
"""

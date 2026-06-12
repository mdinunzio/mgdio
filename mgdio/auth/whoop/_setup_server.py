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

import json
import logging
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import keyring
import requests

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
        return True, "Authorized."
    if resp.status_code == 401:
        return False, "Whoop rejected the access token (401)."
    return False, f"Whoop returned HTTP {resp.status_code}: {resp.text[:200]}"


def _save_app_credentials(client_id: str, client_secret: str) -> None:
    keyring.set_password(
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
            self._send_html(_render_done(True, "Authorized! You can close this tab."))
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
      <a href="https://developer.whoop.com/" target="_blank">
      developer.whoop.com</a> and sign in with your Whoop account.</li>
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

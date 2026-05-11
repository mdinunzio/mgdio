"""Localhost setup server for one-shot YNAB personal-access-token onboarding.

When the user runs ``mgdio auth ynab`` and there's no existing token,
this module starts a tiny HTTP server on ``127.0.0.1`` (random port),
opens the browser at ``/``, and walks the user through:

1. Reading instructions for minting a personal access token at
   https://app.ynab.com/settings/developer.
2. Pasting the token into a single text field.
3. Clicking "Save", which validates the token against ``/v1/user`` and
   returns the validated string to the caller for keyring storage.

The server serves only the local user (``127.0.0.1`` bind), runs in a
background thread, and shuts itself down once the user saves or cancels.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from mgdio.settings import YNAB_API_BASE

logger = logging.getLogger(__name__)


class SetupResult:
    """Holds the outcome of the setup flow, populated by the request handler.

    Attributes:
        token: Populated on successful validation, else ``None``.
        error: Last error message, else ``None``.
        done_event: Set once the flow reaches a terminal state.
    """

    def __init__(self) -> None:
        """Initialize an empty result with an unset done-event."""
        self.token: str | None = None
        self.error: str | None = None
        self.done_event = threading.Event()


def run_setup_flow() -> str:
    """Run the browser-based onboarding flow and return the YNAB token.

    Starts a localhost HTTP server, opens the browser at the instructions
    page, and blocks until the user pastes + saves a token (or cancels).
    The token is validated against ``/v1/user`` before being returned.

    Returns:
        The validated YNAB personal access token.

    Raises:
        RuntimeError: If the user closed the page or validation failed
            irrecoverably.
    """
    result = SetupResult()
    handler_class = _make_handler_class(result)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    server_thread = threading.Thread(
        target=server.serve_forever, name="mgdio-ynab-setup-server", daemon=True
    )
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    logger.info("Opening YNAB setup page at %s", url)
    webbrowser.open(url)

    try:
        result.done_event.wait()
    finally:
        # Give the browser a moment to render the success state.
        time.sleep(0.5)
        server.shutdown()
        server.server_close()

    if result.token is None:
        raise RuntimeError(result.error or "Setup flow did not complete.")
    return result.token


def _validate_token(token: str) -> tuple[bool, str]:
    """Hit YNAB ``/v1/user`` to verify a pasted token.

    Returns:
        Tuple of ``(ok, message)``. ``ok=True`` means the token is valid.
    """
    try:
        resp = requests.get(
            f"{YNAB_API_BASE}/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach YNAB: {exc}"
    if resp.status_code == 200:
        return True, "Token verified."
    if resp.status_code == 401:
        return False, "Token rejected by YNAB (401 unauthorized)."
    return False, f"YNAB returned HTTP {resp.status_code}: {resp.text[:200]}"


def _make_handler_class(result: SetupResult):
    """Build a request handler class closed over the setup state."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            logger.debug(
                "ynab-setup-server %s - %s", self.address_string(), format % args
            )

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                self._send_html(_PAGE)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/save":
                self._handle_save()
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

        def _handle_save(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8_000:
                self._send_json(
                    {"ok": False, "message": "Empty or oversized payload."},
                    status=400,
                )
                return
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send_json(
                    {"ok": False, "message": f"Not valid JSON: {exc}"},
                    status=400,
                )
                return

            token = (parsed.get("token") or "").strip()
            if not token:
                self._send_json(
                    {"ok": False, "message": "Paste your personal access token."},
                    status=400,
                )
                return

            ok, message = _validate_token(token)
            if not ok:
                self._send_json({"ok": False, "message": message}, status=400)
                return

            result.token = token
            self._send_json({"ok": True, "message": message})
            result.done_event.set()

        def _handle_cancel(self) -> None:
            self._send_json({"ok": True})
            if result.token is None:
                result.error = result.error or "Cancelled by user."
            result.done_event.set()

    return _Handler


_PAGE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - YNAB setup</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 760px; margin: 2.5rem auto; padding: 0 1.25rem;
    line-height: 1.55;
  }
  h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
  h2 { font-size: 1.15rem; margin-top: 2rem; }
  code, pre {
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    background: rgba(127,127,127,0.12); padding: 0.1rem 0.35rem;
    border-radius: 4px;
  }
  pre { padding: 0.75rem; overflow-x: auto; }
  ol li { margin: 0.4rem 0; }
  a { color: #2563eb; }
  textarea {
    width: 100%; box-sizing: border-box; padding: 0.6rem 0.75rem;
    border: 1px solid #888; border-radius: 6px; font: inherit;
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    min-height: 4rem; resize: vertical;
  }
  button {
    font: inherit; padding: 0.6rem 1.1rem; border-radius: 6px;
    border: 1px solid #2563eb; background: #2563eb; color: white;
    cursor: pointer;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  #status { margin-top: 1rem; min-height: 1.4rem; }
  .ok { color: #16a34a; }
  .err { color: #dc2626; }
  .note {
    border-left: 4px solid #d97706; padding: 0.5rem 0.85rem;
    background: rgba(217,119,6,0.08); margin: 1rem 0; border-radius: 4px;
  }
</style>
</head>
<body>
<h1>mgdio - YNAB setup</h1>
<p>
  One-time setup to authorize <strong>mgdio</strong> against your YNAB
  account. This page is served from your own machine; nothing leaves
  localhost except the validation request to YNAB itself.
</p>

<h2>1. Mint a personal access token</h2>
<ol>
  <li>Open
      <a href="https://app.ynab.com/settings/developer" target="_blank">
      app.ynab.com/settings/developer</a> (sign in if prompted).</li>
  <li>Click <strong>New Token</strong>.</li>
  <li>Re-enter your YNAB password when asked, then click
      <strong>Generate</strong>.</li>
  <li>Copy the long token string that appears -- YNAB will not show it
      again.</li>
</ol>

<h2>2. Paste it below</h2>
<textarea id="token" placeholder="paste your YNAB personal access token"
          spellcheck="false"></textarea>
<p style="margin-top:0.75rem">
  <button id="save">Save token</button>
  <button id="cancel" style="background:#6b7280;border-color:#6b7280;
          margin-left:0.5rem">Cancel</button>
</p>
<p id="status"></p>

<div class="note">
  When you click <em>Save</em>, mgdio calls
  <code>GET /v1/user</code> on YNAB to verify the token. On success it
  is stored in your OS credential vault (Windows Credential Manager /
  macOS Keychain / Linux Secret Service) under <code>mgdio:ynab</code>.
  Nothing is written to disk.
</div>

<script>
const tokenEl = document.getElementById('token');
const saveBtn = document.getElementById('save');
const cancelBtn = document.getElementById('cancel');
const statusEl = document.getElementById('status');

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || '';
}

saveBtn.addEventListener('click', async () => {
  const token = tokenEl.value.trim();
  if (!token) { setStatus('Paste a token first.', 'err'); return; }
  saveBtn.disabled = true;
  setStatus('Validating against YNAB...');
  try {
    const r = await fetch('/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: token}),
    });
    const data = await r.json();
    if (data.ok) {
      setStatus(
        'Saved! Token stored in your OS keyring. You can close this tab.',
        'ok'
      );
      cancelBtn.disabled = true;
    } else {
      setStatus(data.message || 'Save failed.', 'err');
      saveBtn.disabled = false;
    }
  } catch (err) {
    setStatus('Save failed: ' + err, 'err');
    saveBtn.disabled = false;
  }
});

cancelBtn.addEventListener('click', async () => {
  await fetch('/cancel', {method: 'POST'});
  setStatus('Cancelled. You can close this tab.', 'err');
  saveBtn.disabled = true;
  cancelBtn.disabled = true;
});

tokenEl.focus();
</script>

</body>
</html>
"""

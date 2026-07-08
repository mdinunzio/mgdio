"""Localhost setup server for one-shot Google Maps API-key onboarding.

When the user runs ``mgdio auth maps`` and there's no existing key, this
module starts a tiny HTTP server on ``127.0.0.1`` (random port), opens
the browser at ``/``, and walks the user through:

1. Creating an API key in the Google Cloud Console with the Geocoding
   and Directions APIs enabled.
2. Pasting the key into a single text field.
3. Clicking "Save", which validates the key with a test geocode and
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

from mgdio.settings import MAPS_API_BASE

logger = logging.getLogger(__name__)


class SetupResult:
    """Holds the outcome of the setup flow, populated by the request handler.

    Attributes:
        api_key: Populated on successful validation, else ``None``.
        error: Last error message, else ``None``.
        done_event: Set once the flow reaches a terminal state.
    """

    def __init__(self) -> None:
        """Initialize an empty result with an unset done-event."""
        self.api_key: str | None = None
        self.error: str | None = None
        self.done_event = threading.Event()


def run_setup_flow() -> str:
    """Run the browser-based onboarding flow and return the Maps API key.

    Starts a localhost HTTP server, opens the browser at the instructions
    page, and blocks until the user pastes + saves a key (or cancels).
    The key is validated with a test geocode before being returned.

    Returns:
        The validated Google Maps API key.

    Raises:
        RuntimeError: If the user closed the page or validation failed
            irrecoverably.
    """
    result = SetupResult()
    handler_class = _make_handler_class(result)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    server_thread = threading.Thread(
        target=server.serve_forever, name="mgdio-maps-setup-server", daemon=True
    )
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    logger.info("Opening Maps setup page at %s", url)
    webbrowser.open(url)

    try:
        result.done_event.wait()
    finally:
        # Give the browser a moment to render the success state.
        time.sleep(0.5)
        server.shutdown()
        server.server_close()

    if result.api_key is None:
        raise RuntimeError(result.error or "Setup flow did not complete.")
    return result.api_key


def _validate_key(api_key: str) -> tuple[bool, str]:
    """Verify a pasted key with a test geocode against the Geocoding API.

    Returns:
        Tuple of ``(ok, message)``. ``ok=True`` means the key works and
        the Geocoding API is enabled.
    """
    try:
        resp = requests.get(
            f"{MAPS_API_BASE}/geocode/json",
            params={"address": "New York, NY", "key": api_key},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach Google Maps: {exc}"
    try:
        body = resp.json()
    except ValueError:
        return False, f"Google Maps returned non-JSON (HTTP {resp.status_code})."

    status = body.get("status", "")
    detail = body.get("error_message", "")
    if status in ("OK", "ZERO_RESULTS"):
        return True, "Key verified."
    if status == "REQUEST_DENIED":
        return False, (
            "Request denied. Check the key and that the Geocoding API is "
            "enabled for this project" + (f": {detail}" if detail else ".")
        )
    if status in ("OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT"):
        return False, (
            "Key is over quota / billing may not be enabled"
            + (f": {detail}" if detail else ".")
        )
    return False, f"Google Maps returned status {status}" + (
        f": {detail}" if detail else "."
    )


def _make_handler_class(result: SetupResult):
    """Build a request handler class closed over the setup state."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            logger.debug(
                "maps-setup-server %s - %s", self.address_string(), format % args
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

            api_key = (parsed.get("api_key") or "").strip()
            if not api_key:
                self._send_json(
                    {"ok": False, "message": "Paste your Maps API key."},
                    status=400,
                )
                return

            ok, message = _validate_key(api_key)
            if not ok:
                self._send_json({"ok": False, "message": message}, status=400)
                return

            result.api_key = api_key
            self._send_json({"ok": True, "message": message})
            result.done_event.set()

        def _handle_cancel(self) -> None:
            self._send_json({"ok": True})
            if result.api_key is None:
                result.error = result.error or "Cancelled by user."
            result.done_event.set()

    return _Handler


_PAGE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - Google Maps setup</title>
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
<h1>mgdio - Google Maps setup</h1>
<p>
  One-time setup to authorize <strong>mgdio</strong> against Google Maps
  Platform (Geocoding + Directions). This uses an <strong>API key</strong>,
  not your Google login. This page is served from your own machine;
  nothing leaves localhost except the validation request to Google.
</p>

<h2>1. Create an API key</h2>
<ol>
  <li>Open the
      <a href="https://console.cloud.google.com/google/maps-apis/credentials"
         target="_blank">Google Maps Platform &rarr; Credentials</a>
      page (create or pick a project; billing must be enabled -- Google
      Maps Platform requires a billing account even for the free tier).</li>
  <li>Under <em>APIs &amp; Services &rarr; Library</em>, enable both the
      <strong>Geocoding API</strong> and the <strong>Directions API</strong>.</li>
  <li>Back on <em>Credentials</em>, click
      <strong>Create credentials &rarr; API key</strong> and copy the
      key that appears.</li>
  <li><em>(Recommended)</em> Click <em>Edit API key</em> and, under
      <em>API restrictions</em>, restrict it to just the Geocoding API and
      Directions API.</li>
</ol>

<h2>2. Paste it below</h2>
<textarea id="key" placeholder="paste your Google Maps API key"
          spellcheck="false"></textarea>
<p style="margin-top:0.75rem">
  <button id="save">Save key</button>
  <button id="cancel" style="background:#6b7280;border-color:#6b7280;
          margin-left:0.5rem">Cancel</button>
</p>
<p id="status"></p>

<div class="note">
  When you click <em>Save</em>, mgdio runs a test geocode against Google
  to verify the key works and the Geocoding API is enabled. On success it
  is stored in your OS credential vault (Windows Credential Manager /
  macOS Keychain / Linux Secret Service) under <code>mgdio:maps</code>.
  Nothing is written to disk.
</div>

<script>
const keyEl = document.getElementById('key');
const saveBtn = document.getElementById('save');
const cancelBtn = document.getElementById('cancel');
const statusEl = document.getElementById('status');

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || '';
}

saveBtn.addEventListener('click', async () => {
  const api_key = keyEl.value.trim();
  if (!api_key) { setStatus('Paste a key first.', 'err'); return; }
  saveBtn.disabled = true;
  setStatus('Validating against Google Maps...');
  try {
    const r = await fetch('/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({api_key: api_key}),
    });
    const data = await r.json();
    if (data.ok) {
      setStatus(
        'Saved! Key stored in your OS keyring. You can close this tab.',
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

keyEl.focus();
</script>

</body>
</html>
"""

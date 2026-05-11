"""Localhost setup server for one-shot Google OAuth onboarding.

Drives first-time setup for the unified Google identity used by every
mgdio Google service (Gmail, Calendar, Sheets). When the user runs
``mgdio auth google`` and there's no existing token, this module:

1. Starts a tiny HTTP server on ``127.0.0.1`` (random port).
2. Opens the browser at ``/`` to a stylized instructions page.
3. Accepts ``client_secret.json`` via drag-and-drop.
4. Triggers Google's OAuth consent flow when the user clicks Authorize.

The server serves only the local user (``127.0.0.1`` bind), runs in a
background thread, and shuts itself down once auth completes (or the
user cancels). The OAuth callback uses Google's
``InstalledAppFlow.run_local_server(port=0)`` on a *separate* port -- the
two servers don't collide because the OAuth one is short-lived.

Threading note: ``InstalledAppFlow.run_local_server`` blocks until the
callback fires. We run it on a worker thread so the setup server's
request handler can return immediately.

The ``run_setup_flow`` entry point takes a ``client_secret_path`` and
``scopes`` list, so this module is provider-neutral and could be reused
by any future installed-app OAuth provider that wants the same UX.
"""

from __future__ import annotations

import html
import json
import logging
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL_SECONDS = 1.5


class SetupResult:
    """Holds the outcome of the setup flow, populated by the request handler.

    Attributes:
        credentials: Populated on successful OAuth completion, else ``None``.
        error: Last error message produced by upload or OAuth, else ``None``.
        done_event: Set once the flow reaches a terminal state.
    """

    def __init__(self) -> None:
        """Initialize an empty result with an unset done-event."""
        self.credentials: Credentials | None = None
        self.error: str | None = None
        self.done_event = threading.Event()


def run_setup_flow(
    client_secret_path: Path,
    scopes: list[str],
) -> Credentials:
    """Run the browser-based onboarding flow and return OAuth credentials.

    Starts a localhost HTTP server, opens the browser at the instructions
    page, and blocks until the user finishes (or aborts). The downloaded
    ``client_secret.json`` is written to ``client_secret_path``; the
    returned credentials are *not* persisted -- the caller stores them.

    Args:
        client_secret_path: Where to save the uploaded client_secret.json.
        scopes: OAuth scopes to request during consent.

    Returns:
        Valid ``google.oauth2.credentials.Credentials``.

    Raises:
        RuntimeError: If the user closed the page or OAuth failed.
    """
    result = SetupResult()
    handler_class = _make_handler_class(client_secret_path, scopes, result)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    server_thread = threading.Thread(
        target=server.serve_forever, name="mgdio-setup-server", daemon=True
    )
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    logger.info("Opening setup page at %s", url)
    webbrowser.open(url)

    try:
        result.done_event.wait()
    finally:
        # Give the browser a moment to receive the success page before tearing down.
        time.sleep(0.5)
        server.shutdown()
        server.server_close()

    if result.credentials is None:
        raise RuntimeError(result.error or "Setup flow did not complete.")
    return result.credentials


def _make_handler_class(
    client_secret_path: Path,
    scopes: list[str],
    result: SetupResult,
):
    """Build a request handler class closed over the setup state."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            logger.debug("setup-server %s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                self._send_html(_render_page(client_secret_path))
            elif self.path == "/status":
                self._send_status()
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/upload":
                self._handle_upload()
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

        def _send_status(self) -> None:
            if result.credentials is not None:
                self._send_json({"state": "authorized"})
            elif result.error:
                self._send_json({"state": "error", "message": result.error})
            elif client_secret_path.exists():
                self._send_json({"state": "uploaded"})
            else:
                self._send_json({"state": "waiting"})

        def _handle_upload(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 256_000:
                self._send_json(
                    {"ok": False, "message": "Empty or oversized upload."},
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

            if not _looks_like_client_secret(parsed):
                self._send_json(
                    {
                        "ok": False,
                        "message": (
                            "This doesn't look like a Google OAuth client_secret "
                            "file (expected an 'installed' or 'web' top-level key "
                            "with client_id and client_secret)."
                        ),
                    },
                    status=400,
                )
                return

            client_secret_path.parent.mkdir(parents=True, exist_ok=True)
            client_secret_path.write_text(
                json.dumps(parsed, indent=2), encoding="utf-8"
            )
            logger.info("Saved client_secret.json to %s", client_secret_path)
            self._send_json({"ok": True})

        def _handle_authorize(self) -> None:
            if not client_secret_path.exists():
                self._send_json(
                    {"ok": False, "message": "Upload client_secret.json first."},
                    status=400,
                )
                return
            # Respond immediately; OAuth runs on a background thread so the
            # browser is free to follow Google's redirect.
            self._send_json({"ok": True})
            threading.Thread(
                target=_run_oauth_in_background,
                args=(client_secret_path, scopes, result),
                name="mgdio-oauth-flow",
                daemon=True,
            ).start()

        def _handle_cancel(self) -> None:
            self._send_json({"ok": True})
            if result.credentials is None:
                result.error = result.error or "Cancelled by user."
            result.done_event.set()

    return _Handler


def _run_oauth_in_background(
    client_secret_path: Path,
    scopes: list[str],
    result: SetupResult,
) -> None:
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path), scopes=scopes
        )
        creds = flow.run_local_server(port=0, open_browser=True)
        result.credentials = creds
        logger.info("OAuth flow completed.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("OAuth flow failed")
        result.error = f"OAuth flow failed: {exc}"
    finally:
        result.done_event.set()


def _looks_like_client_secret(parsed: object) -> bool:
    if not isinstance(parsed, dict):
        return False
    for key in ("installed", "web"):
        section = parsed.get(key)
        if (
            isinstance(section, dict)
            and "client_id" in section
            and ("client_secret" in section)
        ):
            return True
    return False


def _render_page(client_secret_path: Path) -> str:
    return _PAGE_TEMPLATE.format(
        client_secret_path=html.escape(str(client_secret_path))
    )


_PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - Google setup</title>
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
  pre {{ padding: 0.75rem; overflow-x: auto; }}
  ol li {{ margin: 0.4rem 0; }}
  .path {{
    display: inline-block; background: rgba(127,127,127,0.18);
    padding: 0.25rem 0.5rem; border-radius: 4px; word-break: break-all;
  }}
  .note {{
    border-left: 4px solid #d97706; padding: 0.5rem 0.85rem;
    background: rgba(217,119,6,0.08); margin: 1rem 0; border-radius: 4px;
  }}
  #drop {{
    margin: 1.25rem 0; padding: 2rem; border: 2px dashed #888;
    border-radius: 8px; text-align: center; cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }}
  #drop.hover {{ border-color: #2563eb; background: rgba(37,99,235,0.08); }}
  #drop.ok {{ border-color: #16a34a; background: rgba(22,163,74,0.08); }}
  #drop.err {{ border-color: #dc2626; background: rgba(220,38,38,0.08); }}
  button {{
    font: inherit; padding: 0.6rem 1.1rem; border-radius: 6px;
    border: 1px solid #2563eb; background: #2563eb; color: white;
    cursor: pointer;
  }}
  button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  #status {{ margin-top: 1rem; min-height: 1.4rem; }}
  .ok {{ color: #16a34a; }}
  .err {{ color: #dc2626; }}
</style>
</head>
<body>
<h1>mgdio - Google setup</h1>
<p>
  One-time setup to authorize <strong>mgdio</strong> against your Google
  account. A single consent covers <strong>Gmail</strong>,
  <strong>Calendar</strong>, and <strong>Sheets</strong>.
  This page is served from your own machine; nothing leaves localhost.
</p>

<h2>1. Create / select a Google Cloud project</h2>
<ol>
  <li>Open <a href="https://console.cloud.google.com/" target="_blank">
      console.cloud.google.com</a> and create or pick a project.</li>
  <li>Under <em>APIs &amp; Services -&gt; Library</em>, enable all three
      APIs: <strong>Gmail API</strong>,
      <strong>Google Calendar API</strong>, and
      <strong>Google Sheets API</strong>.</li>
</ol>

<h2>2. Configure the app under Google Auth Platform</h2>
<ol>
  <li><em>Branding</em>: fill in app name and support email.</li>
  <li><em>Audience</em>: User type
      <strong>External</strong>; add yourself under <em>Test users</em>;
      then click <strong>Publish app</strong>. (Apps left in
      <em>Testing</em> mode have their refresh tokens revoked every
      7 days.)</li>
  <li><em>Data Access</em>: click <em>Add or remove scopes</em> and add
      all three of:
      <ul>
        <li><code>https://www.googleapis.com/auth/gmail.modify</code></li>
        <li><code>https://www.googleapis.com/auth/calendar</code></li>
        <li><code>https://www.googleapis.com/auth/spreadsheets</code></li>
      </ul>
  </li>
</ol>

<h2>3. Create an OAuth client ID</h2>
<ol>
  <li>Go to <em>Google Auth Platform -&gt; Clients -&gt; Create client</em>.</li>
  <li>Application type: <strong>Desktop app</strong>. (This lets the
      OAuth callback use any localhost port.)</li>
  <li>Click <em>Download JSON</em>.</li>
</ol>

<h2>4. Drop the file below</h2>
<p>The file is saved to <span class="path">{client_secret_path}</span>
   for you - no manual copying needed.</p>

<div id="drop">
  Drag &amp; drop <code>client_secret.json</code> here<br>
  <small>or click to choose a file</small>
  <input id="file" type="file" accept=".json,application/json" hidden>
</div>

<h2>5. Authorize</h2>
<p>After uploading, click below to open Google's consent screen in a new
   tab. Once you approve, your token is stored in your OS keyring and
   this page closes itself.</p>
<button id="authorize" disabled>Authorize with Google</button>
<button id="cancel" style="background:#6b7280;border-color:#6b7280;
        margin-left:0.5rem">Cancel</button>
<p id="status"></p>

<script>
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const authBtn = document.getElementById('authorize');
const cancelBtn = document.getElementById('cancel');
const statusEl = document.getElementById('status');

function setStatus(text, cls) {{
  statusEl.textContent = text;
  statusEl.className = cls || '';
}}

drop.addEventListener('click', () => fileInput.click());
drop.addEventListener('dragover', (e) => {{
  e.preventDefault(); drop.classList.add('hover');
}});
drop.addEventListener('dragleave', () => drop.classList.remove('hover'));
drop.addEventListener('drop', (e) => {{
  e.preventDefault();
  drop.classList.remove('hover');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
}});
fileInput.addEventListener('change', () => {{
  if (fileInput.files.length) handleFile(fileInput.files[0]);
}});

async function handleFile(file) {{
  setStatus('Uploading ' + file.name + '...');
  const text = await file.text();
  try {{
    const r = await fetch('/upload', {{ method: 'POST', body: text }});
    const data = await r.json();
    if (data.ok) {{
      drop.classList.remove('err'); drop.classList.add('ok');
      setStatus('Saved. Click Authorize to continue.', 'ok');
      authBtn.disabled = false;
    }} else {{
      drop.classList.remove('ok'); drop.classList.add('err');
      setStatus(data.message || 'Upload rejected.', 'err');
    }}
  }} catch (err) {{
    drop.classList.add('err');
    setStatus('Upload failed: ' + err, 'err');
  }}
}}

authBtn.addEventListener('click', async () => {{
  authBtn.disabled = true;
  setStatus('Opening Google consent screen...');
  const r = await fetch('/authorize', {{ method: 'POST' }});
  const data = await r.json();
  if (!data.ok) {{
    setStatus(data.message || 'Could not start authorization.', 'err');
    authBtn.disabled = false;
    return;
  }}
  poll();
}});

cancelBtn.addEventListener('click', async () => {{
  await fetch('/cancel', {{ method: 'POST' }});
  setStatus('Cancelled. You can close this tab.', 'err');
  authBtn.disabled = true;
  cancelBtn.disabled = true;
}});

async function poll() {{
  try {{
    const r = await fetch('/status');
    const data = await r.json();
    if (data.state === 'authorized') {{
      setStatus('Authorized! Token saved to your OS keyring. '
                + 'You can close this tab.', 'ok');
      cancelBtn.disabled = true;
      return;
    }}
    if (data.state === 'error') {{
      setStatus(data.message || 'Authorization failed.', 'err');
      authBtn.disabled = false;
      return;
    }}
  }} catch (err) {{
    /* server may have shut down right after success - that's ok */
    return;
  }}
  setTimeout(poll, {heartbeat_ms});
}}
</script>

<p class="note">
  Your OAuth token is stored in your OS credential vault (Windows
  Credential Manager / macOS Keychain / Linux Secret Service). The
  <code>client_secret.json</code> file you uploaded is application
  config, not a per-user secret.
</p>

</body>
</html>
""".replace("{heartbeat_ms}", str(int(_HEARTBEAT_INTERVAL_SECONDS * 1000)))

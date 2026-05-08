"""Render a stylized HTML help page for first-time Gmail OAuth setup.

Used when ``client_secret.json`` is missing on the first run. Writes the
page to a temp file and opens it in the user's default browser so they
can follow the Google Cloud Console steps without leaving their flow.
"""

from __future__ import annotations

import html
import tempfile
import webbrowser
from pathlib import Path

_PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mgdio - Gmail setup</title>
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
</style>
</head>
<body>
<h1>mgdio - Gmail setup</h1>
<p>
  No <code>client_secret.json</code> was found. Follow these one-time steps
  to authorize <strong>mgdio</strong> against your personal Gmail account.
</p>

<h2>1. Create / select a Google Cloud project</h2>
<ol>
  <li>Open <a href="https://console.cloud.google.com/" target="_blank">
      console.cloud.google.com</a> and create or pick a project.</li>
  <li>Under <em>APIs &amp; Services -&gt; Library</em>, enable
      <strong>Gmail API</strong>.</li>
</ol>

<h2>2. Configure the OAuth consent screen</h2>
<ol>
  <li>Go to <em>APIs &amp; Services -&gt; OAuth consent screen</em>.</li>
  <li>User type: <strong>External</strong>. Fill in app name + your email.</li>
  <li>Add the scope
      <code>https://www.googleapis.com/auth/gmail.modify</code>.</li>
  <li>Add yourself as a test user.</li>
  <li><strong>Click "Publish app"</strong> so refresh tokens do not expire
      after 7 days. (Apps left in <em>Testing</em> mode have refresh
      tokens revoked weekly.)</li>
</ol>

<h2>3. Create an OAuth client ID</h2>
<ol>
  <li>Go to <em>APIs &amp; Services -&gt; Credentials -&gt; Create
      Credentials -&gt; OAuth client ID</em>.</li>
  <li>Application type: <strong>Desktop app</strong>.</li>
  <li>Click <em>Download JSON</em>.</li>
</ol>

<h2>4. Drop the file in mgdio's data directory</h2>
<p>Save (or rename) the downloaded file to:</p>
<pre class="path">{client_secret_path}</pre>
<div class="note">
  This file is application config, not a per-user secret. The OAuth token
  itself is stored separately in your OS credential vault (Windows
  Credential Manager / macOS Keychain / Linux Secret Service).
</div>

<h2>5. Re-run mgdio</h2>
<pre>uv run mgdio auth</pre>
<p>
  A browser tab will open for Google's consent screen. After approving,
  you will be redirected to a localhost URL and mgdio will print
  <code>Authenticated.</code>.
</p>

</body>
</html>
"""


def render_to_temp_and_open(client_secret_path: Path) -> Path:
    """Write the help page to a temp HTML file and open it in a browser.

    Args:
        client_secret_path: Where the user must drop ``client_secret.json``.
            Inserted into the page so the path is copy-pasteable.

    Returns:
        Path to the temp HTML file (kept on disk so the browser can read it).
    """
    rendered = _PAGE_TEMPLATE.format(
        client_secret_path=html.escape(str(client_secret_path))
    )
    tmp = Path(
        tempfile.NamedTemporaryFile(
            prefix="mgdio_gmail_setup_", suffix=".html", delete=False
        ).name
    )
    tmp.write_text(rendered, encoding="utf-8")
    webbrowser.open(tmp.as_uri())
    return tmp

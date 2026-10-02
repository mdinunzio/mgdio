# Installation

`mgdio` is not on PyPI yet. Install it straight from GitHub.

## Into another project

With `uv` (recommended), from inside your target project:

```bash
# HTTPS (works without an SSH key)
uv add "git+https://github.com/mdinunzio/mgdio.git"

# SSH (if your GitHub SSH key is set up)
uv add "git+ssh://git@github.com/mdinunzio/mgdio.git"

# Pin to a branch, tag, or commit
uv add "git+https://github.com/mdinunzio/mgdio.git@main"
uv add "git+https://github.com/mdinunzio/mgdio.git@v0.5.0"
uv add "git+https://github.com/mdinunzio/mgdio.git@<commit-sha>"

# Optional DataFrame backend for Sheets
uv add "mgdio[sheets-pandas] @ git+https://github.com/mdinunzio/mgdio.git"
uv add "mgdio[sheets-polars] @ git+https://github.com/mdinunzio/mgdio.git"
```

With plain `pip`:

```bash
pip install "git+https://github.com/mdinunzio/mgdio.git"
pip install "git+https://github.com/mdinunzio/mgdio.git@main"
pip install "mgdio[sheets-pandas] @ git+https://github.com/mdinunzio/mgdio.git"
```

Verify the install:

```bash
python -c "from mgdio.auth.google import get_credentials; print('OK')"
mgdio --help
```

Upgrade later (re-fetches the latest commit on the requested ref):

```bash
uv add --upgrade "git+https://github.com/mdinunzio/mgdio.git"
# or
pip install --upgrade --force-reinstall "git+https://github.com/mdinunzio/mgdio.git"
```

## As a global command

To type `mgdio gmail list --max 5` from anywhere, without `uv run` or an
activated venv, install it as a tool:

```bash
uv tool install "git+https://github.com/mdinunzio/mgdio.git"   # recommended
pipx install "git+https://github.com/mdinunzio/mgdio.git"      # same idea
```

Upgrade with `uv tool upgrade mgdio` (or `pipx upgrade mgdio`).

Other ways to invoke the CLI:

```bash
uv run mgdio gmail list --max 5        # inside a uv project that depends on mgdio
python -m mgdio gmail list --max 5     # inside any activated venv
```

!!! warning "Stale parallel installs"
    A `uv tool` shim can shadow a newer project venv. `mgdio --version` prints
    the running install's version **and path**, so you can tell which one you
    are hitting.

## Optional extras

| Extra | Adds | Use when |
| --- | --- | --- |
| `sheets-pandas` | `pandas` | `fetch_values(..., as_="pandas")` |
| `sheets-polars` | `polars` | `fetch_values(..., as_="polars")` |
| `dev` | pytest, black, isort, flake8, both DataFrame libs | Working on mgdio itself |
| `docs` | mkdocs, Material, mkdocstrings, mkdocs-click | Building this site |

## Develop on this repo

```bash
git clone git@github.com:mdinunzio/mgdio.git
cd mgdio
uv sync --extra dev
uv pip install -e .        # registers the `mgdio` console script
uv run pytest -ra          # unit suite; never touches your real keyring
```

### Build the docs locally

```bash
uv sync --extra docs
uv run mkdocs serve        # live-reloading preview at http://127.0.0.1:8000
uv run mkdocs build --strict
```

The API reference is generated from docstrings by
[mkdocstrings](https://mkdocstrings.github.io/), so keeping docstrings
accurate keeps the reference accurate. The site deploys to GitHub Pages from
`main` via `.github/workflows/docs.yml`.

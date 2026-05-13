"""Allow ``python -m mgdio ...`` as an alias for the ``mgdio`` console script.

Useful inside an activated venv (where ``mgdio.exe``/``mgdio`` is on PATH but
you'd rather type one explicit invocation) and inside CI/test environments
where setting up a console-script symlink is awkward.
"""

from mgdio.cli import cli

if __name__ == "__main__":
    cli()

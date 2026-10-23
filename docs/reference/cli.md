# Command line

The `mgdio` console script (also `python -m mgdio`) exposes every service as a
command group. The sections below are generated from the click definitions in
`mgdio.cli`, so they always match `--help`.

Google service commands accept `--profile <slug>`; see
[profiles](../auth.md#multiple-google-accounts-profiles).

::: mkdocs-click
    :module: mgdio.cli
    :command: cli
    :prog_name: mgdio
    :depth: 1
    :style: table

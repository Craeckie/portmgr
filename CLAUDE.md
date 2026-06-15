# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`portmgr` is a Python CLI tool that wraps `docker compose`, letting you run compose commands recursively across a directory tree. A `dckrsub.yml` file in any directory lists subdirectories portmgr should descend into; directories containing a `docker-compose.yml` / `docker-compose.yaml` are leaf nodes where commands are executed.

## Development setup

Uses [uv](https://docs.astral.sh/uv/) for packaging (Python 3.12).

```bash
uv sync                    # install dependencies into .venv
uv run portmgr             # run from source
```

## Build & publish

```bash
uv build                   # produces dist/
uv publish                 # upload to PyPI
# or use the helper:
./release.sh
```

There are no tests and no linter configured.

## Architecture

```
src/portmgr/
  portmgr.py       # entry point & CLI: traverses the directory tree, loads commands, dispatches
  wrapper.py       # thin helpers around `docker compose` / `docker buildx` subprocesses
  __init__.py      # re-exports main, command_list, bcolors, runCompose, runBuildx
  commands/        # one file per command letter; each registers itself in command_list
```

### How commands are registered

`portmgr.py` imports every `.py` file in `commands/` at startup via `importlib`. Each module runs top-level code that adds an entry to `command_list` (imported from `portmgr`):

```python
command_list['u'] = {'hlp': '...', 'ord': 'nrm', 'fnc': func}
```

`ord` is `'nrm'` (normal traversal order) or `'rev'` (reversed — used by `down`/`stop` so dependent stacks shut down safely).

Secret-related commands use uppercase letters (`E`, `D`, `S`, `R`) to visually distinguish them from regular docker-compose wrappers.

### Directory traversal

`traverse()` walks from `base_directory` (default: `cwd`). At each directory it checks for:
1. A `dckrsub.yml` → recurse into listed subdirectories.
2. A `docker-compose.yml` / `docker-compose.yaml` → add to `action_list` as a target.

The filenames are overridable via env vars `PORTMGR_SUB_NAME` and `PORTMGR_COMPOSE_NAME`.

### Environment variables

| Variable | Effect |
|---|---|
| `PORTMGR_SUB_NAME` | Override `dckrsub.yml` filename(s), space/comma/semicolon-separated |
| `PORTMGR_COMPOSE_NAME` | Override compose filename(s), comma-separated |
| `PORTMGR_IN_SCRIPT` | Set to `true` to pass `--ansi never` to all compose calls |
| `PORTMGR_MULTI_PLATFORM` | Platform string for `docker buildx bake` (e.g. `linux/amd64,linux/arm64`) used by the `r` command |
| `PORTMGR_CLEAN_AFTER_PUSH` | Set to `true` to prune all Docker objects after each push in `r` command |

### Adding a new command

Create `src/portmgr/commands/<letter>.py`, import `command_list` and `runCompose` from `portmgr`, define a `func(action)` that returns an exit code (0 = success), and register it:

```python
from portmgr import command_list
from portmgr.wrapper import runCompose

def func(action):
    return runCompose(['your-subcommand'])

command_list['y'] = {'hlp': 'Short description', 'ord': 'nrm', 'fnc': func}
```

The `action` dict has keys `directory` (absolute path) and `relative` (path relative to base).

**Note:** `-B` is reserved by the CLI as the base directory flag (`portmgr -B /some/path u`). Avoid registering `B` as a command letter.

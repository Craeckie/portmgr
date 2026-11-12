# Changelog

What changed in each release of portmgr. The section of a version is also the body of its GitHub release, so a version bump in `pyproject.toml` always comes with its section here.

## [Unreleased]

## [1.16.0] - 2026-11-12

### Added
- `r --no-cache` rebuilds every layer (`compose build --no-cache`, `buildx bake --no-cache`). `--pull` alone refreshes `FROM` but keeps a cached `RUN apt-get install` layer, so distro-package security fixes in a locally built image can lag until the base image changes.

### Fixed
- `r` no longer triggers Docker Compose's deprecation warning for `--ignore-push-failures`; it pushes with `--ignore-missing`. A failed push now shows as `Error pushing <service>!` instead of passing silently.

## [1.15.0] - 2026-11-02

### Added
- `PORTMGR_LOG_DIR` writes each stack's output to its own log file and leaves one status line per stack on stdout: `-> <stack> OK|FAILED|SKIPPED (3m12s)`.
- `PORTMGR_RESULTS` appends one JSON line per stack: stack, command, exit code, status, start, duration, log file and, for `r` and `b`, the images the stack builds.
- `PORTMGR_STOP_FILE` skips the remaining stacks once the file exists, so a watcher can stop a run whose failures all have the same cause.

### Fixed
- In a cron job or any other pipe, `-> <stack>` and portmgr's error lines now come before that stack's docker output instead of all together at the end of the log.
- `b` passes the shell's environment to `docker compose build` again (it used to pass only the two BuildKit variables, dropping `PATH`, `HOME` and `DOCKER_CONFIG`).

## [1.14.0] - 2026-11-02

### Fixed
- `r` and `b` work on a host that can't unseal a stack's `.env` or its `extends` files: they no longer stop at `docker compose config`, which needs both just to list the services.
- `portmgr E pass` seals the file `pass`. Before, a file name made only of command letters (`pass`, `dup`) was run as commands: `E pass` pulled, opened the attach picker and stopped the stack.

### Changed
- The command line follows tar/getopt rules: `pul`, `-pul`, `-p -u -l` and `pu -l` all work, a word of command letters counts only in first position, and everything after the commands is an argument.
- A stray word is an error (exit 2) and runs nothing: `portmgr l db` no longer runs logs, down and build, and `portmgr u wiki` no longer starts every stack.
- `D --force` is the only spelling; `--force D` is an error.
- `r` and `b` read each service's `build`, `image` and `platform` from the compose file itself and build from `.portmgr-build.yml`, a temporary file next to it holding only those; variables in them still come from `.env` and the shell.
- A service whose `build:` comes only through `extends` is no longer built by `r` and `b`; give it its own `build:`.
- If the compose file can't be read as YAML, `r` and `b` fall back to `docker compose config` with a one-line note.

## [1.13.0] - 2026-10-22

### Added
- Per-host sealing: with a `seal-recipients.yml`, each file is sealed only to the SSH keys of the hosts that run it, plus a recovery key, so a host can unseal its own secrets and nothing else. The hosts come from path rules or from each host's `dckrsub-<host>.yml` chain. See [docs/sealing.md](https://github.com/Craeckie/portmgr/blob/master/docs/sealing.md).
- `portseal` command: `portseal e` seals files, `portseal d` unseals every `*.age` below a path, `portseal k` reseals files whose recipients changed (also from the passphrase, without writing plaintext), and `portseal s` shows who can unseal each file. It works outside compose trees too.
- `PORTMGR_IDENTITY` names the private keys to unseal with (default `~/.ssh/id_ed25519`); a passphrase-protected age key file asks for its passphrase.

### Changed
- `D` also unseals files in subdirectories of a stack, such as `config/settings.yml.age`, and skips files that weren't sealed for this host instead of failing.
- Files without a `seal-recipients.yml` are still sealed with `PORTMGR_PASSPHRASE`, and passphrase-sealed files keep unsealing as before.

## [1.12.0] - 2026-10-20

### Changed
- `dckrsub.yml` is always followed, also when `PORTMGR_SUB_NAME` names other files. `PORTMGR_SUB_NAME=dckrsub-web.yml` now means `dckrsub-web.yml` plus `dckrsub.yml` in every directory, so the files a host reads no longer depend on whether you remembered to list `dckrsub.yml`.

## [1.11.1] - 2026-09-25

### Fixed
- `R` works with MySQL images that only ship the `mysql` client, such as `mysql/mysql-server`, instead of failing with an empty error message.
- `R` changes the password of every host entry of an account (`root@localhost` and `root@%` alike), so no entry is left on the old password.
- `R` writes the new password to the variable the compose file reads: `MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASS}"` updates `MYSQL_ROOT_PASS` in `.env`, not `MYSQL_ROOT_PASSWORD`. Values that mix a reference with other text are not rotated.
- `R` on postgres works when no database is named after the user.
- Failed commands inside the container report their exit code and output.

### Changed
- `R` prints the old and new value of every rotated password on separate lines, also when a service was only partly rotated, so you can update other places that use it. The output contains the passwords in clear text.

## [1.11.0] - 2026-09-25

### Added
- `M` moves literal `environment:` values from the compose file into `.env` and replaces them with `"${NAME}"`, so only `.env` needs sealing. It asks which values to move, with secret-looking keys preselected, shows a preview and leaves the rest of the compose file untouched, comments included.

## [1.10.1] - 2026-09-25

### Changed
- A `.migrated` marker always makes `S` report a service as `DONE`, even if the compose file still contains something that looks like a secret. The `INCONSISTENT` state is gone.
- `E` no longer adds the sealed file to `.gitignore`; make sure `.env` is ignored yourself.

## [1.10.0] - 2026-06-15

### Added
- `R` rotates postgres and mariadb passwords: it sets a new random password in the running container and writes it to `.env`.

### Changed
- The secret commands are uppercase: `e` → `E` (seal), `x` → `D` (unseal), `m` → `S` (status).

## Earlier versions

See the [GitHub releases](https://github.com/Craeckie/portmgr/releases).

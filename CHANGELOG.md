# Changelog

What changed in each release of portmgr. The section of a version is also the body of its GitHub release, so a version bump in `pyproject.toml` always comes with its section here.

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

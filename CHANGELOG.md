# Changelog

What changed in each release of portmgr. The section of a version is also the body of its GitHub release, so a version bump in `pyproject.toml` always comes with its section here.

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

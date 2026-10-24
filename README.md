# portmgr
portmgr is a wrapper around [docker-compose](https://docs.docker.com/compose/) that allows running typical docker-compose commands recursively. Additionally, it shortens commands to a single letter.

Let's say you have organized your compose files like this, you just add a `dckrsub.yml` in each parent folder:
<pre>
docker/
├── <b>dckrsub.yml</b>
├── reverse-proxy/
│   └── docker-compose.yml
├── storage
│   ├── <b>dckrsub.yml</b>
│   ├── nextcloud/
│   │   └── docker-compose.yml
│   └── immich/
│       └── docker-compose.yml
└── scripts
</pre>

Each `dckrsub.yml` has a list of subdirectories, which portmgr should decend into.
For example, the `dckrsub.yml` in `docker/` might look like this:
```yaml
- reverse-proxy
- storage
```

And the `dckrsub.yml` in `docker/storage/` like this:
```yaml
- nextcloud
- immich
```

Now, if you run `portmgr u` in `docker/` it will run `docker compose up -d` in `reverse-proxy/`, `storage/nextcloud/` and `storage/immich/`.

portmgr starts from the current directory, so when running it in `docker/storage/`, it will run `docker compose` only in `nextcloud/` and `immich/`. You can also use it in a directory with a `docker-compose.yml` as a shortener for docker-compose commands.

### One tree for several hosts
To deploy a different set of stacks on each host from the same tree, set `PORTMGR_SUB_NAME` to a host-specific file name, e.g. `PORTMGR_SUB_NAME=dckrsub-web.yml`. In every directory portmgr then follows `dckrsub-web.yml` **and** `dckrsub.yml`, if they exist, and runs each stack once. So `dckrsub.yml` lists what every host runs, and `dckrsub-<host>.yml` adds what only that host runs. Several names can be given, separated by spaces, commas or semicolons; `dckrsub.yml` is always followed last.

### Commands
The following commands are available. The respective docker-compose commands are in brackets.

```
  u   Create and start containers (up)
  p   Pull images (pull)
  s   Stop services (stop)
  d   Stop and remove containers (down)
  l   Show container logs (logs)
  a   Run shell in container (exec -it <service> sh)
  b   Build images (build)
  c   List containers (ps)
  t   List processes in containers (top)
  r   Build and push to registry (build, push)
  v   Scan container images for vulnerabilities
  E   Encrypt/seal secret file(s) with age (requires portmgr[secrets])
  D   Decrypt/unseal sealed secret files (requires portmgr[secrets])
  S   Show secret migration status (requires portmgr[secrets])
  M   Move literal environment values from the compose file into .env
  R   Rotate postgres/mariadb passwords and write new values to .env
```

You combine multiple commands. For example `portmgr dul`, runs docker compose with `down`, `up` and `logs`, thus stopping, removing and starting all containers and then showing the logs.

Commands are read the way `tar` reads its options: `dul`, `-dul`, `-d -u -l` and `du -l` are the same, but a word of command letters only counts in first position. Everything after the commands is an argument, never a command, so `portmgr E pass` seals the file `pass`. Only `E` (files) and `D` (`--force`) take arguments; a stray word such as `portmgr du l` is an error and runs nothing.

### Installation
```
sudo pip install portmgr
```

Or build it from source (here using the latest commit on master branch)
```
sudo pip install https://github.com/Craeckie/portmgr.git
```

### Sealing secrets

portmgr can encrypt secret-bearing files (`.env`, config files) with [age](https://age-encryption.org/) so they are safe to commit to git. Decryption happens once at setup time; the plaintext files remain on disk for Docker to use normally. With a `seal-recipients.yml`, each file is sealed only to the hosts that run it (their SSH keys) plus a recovery key; without one, all files share one passphrase. [docs/sealing.md](https://github.com/Craeckie/portmgr/blob/master/docs/sealing.md) covers the recipients file, host and recovery keys, adding hosts and moving from a passphrase.

**Requires the `secrets` extra:**
```
pip install portmgr[secrets]
```

**Move secrets out of the compose file first** (run inside a service directory, or above it to go through every stack):
```
portmgr M
```
Lists each literal `environment:` value with secret-looking keys (password, token, key, …) preselected, asks which to move, previews the result and asks for confirmation. Each chosen value is appended to `.env` (created with mode 600 if missing) and replaced in the compose file with `"${NAME}"`; nothing else in the compose file changes, comments included. `NAME` is the key itself, or `<SERVICE>_<KEY>` when that name is already used with another value, is referenced elsewhere in the file, or is set in your shell (which would override `.env`). Values that already reference a variable, span several lines, use YAML anchors or tags, or that compose would re-type (`True`, `0o17`, `1.50`, …; quote them to move them) are left alone with a note. Then seal `.env` as below and commit the compose file.

**Seal a file** (run inside a service directory):
```
portmgr E .env
```
This creates `.env.age` and writes a `.migrated` marker. Commit the `.age` file and `.migrated`; never commit the plaintext — `E` does not touch `.gitignore`, so make sure `.env` is ignored yourself.

**Decrypt on a new server** (run from any ancestor directory):
```
portmgr D
```
Recurses via `dckrsub.yml` and decrypts every `*.age` in each stack's directory and below it whose plaintext is missing. Files not sealed for this host are skipped. Use `portmgr D --force` to overwrite existing plaintext from the sealed copy.

**Outside a compose tree, or for the whole tree at once**, use `portseal` (installed with portmgr):
```
portseal e <file>…        # seal
portseal d [path…]        # unseal every *.age below the paths
portseal k [path…]        # reseal files whose recipients changed
portseal s [path…]        # show who can unseal each file
```

**Check migration progress:**
```
portmgr S
```
Reports `DONE`, `PENDING`, or `CLEAN` for each service and prints a summary tally. A `.migrated` marker always means `DONE`, even if the compose file still contains what looks like a secret — create it by hand for services that need no sealing. `CLEAN` only means nothing was *detected*; `portmgr u`'s footer still counts a `CLEAN` service as unsealed until it has a `.migrated`.

**Rotate database passwords:**
```
portmgr R
```
Finds postgres and mariadb/mysql services in each compose stack, generates a new random password, runs `ALTER USER` in the running container, and writes the new value(s) to `.env`. For mariadb/mysql it uses the `mariadb` client, or `mysql` where that is the only one (e.g. `mysql/mysql-server`), and changes the password of every host entry of the account (`root@localhost` and `root@%` alike). The value goes into `.env` under the variable the compose file reads: `MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASS}"` updates `MYSQL_ROOT_PASS`. A value that mixes a reference with other text (`pre${X}`) is not rotated. If a password was previously hardcoded in the compose file rather than referenced via `${VAR}`, a warning is printed reminding you to update the compose file to use the variable reference.

Every rotated password is printed under its `.env` name, with the old and the new value each on its own `old:` / `new:` line, also when only part of a service could be rotated, so you can replace the old value wherever else it is configured. The output contains the passwords in clear text; keep it out of logs you share. Re-seal `.env` with `portmgr E .env` afterwards if you keep a `.env.age`.

**Keys:** files sealed to host keys are unsealed with `~/.ssh/id_ed25519`, or the keys in `PORTMGR_IDENTITY` (comma-separated paths). For passphrase-sealed files portmgr prompts once and caches the passphrase for the rest of the run; for non-interactive use, set `PORTMGR_PASSPHRASE=<passphrase>`.

After running `portmgr u`, a footer line is printed if any services have not yet been sealed.

### Tipps
If you use portmgr a lot like me, you might want to shorten it to one letter. For bash, you can add `alias p='portmgr'` to `~/.bashrc`. For fish-shell you can add `abbr p portmgr` to `~/.config/fish/config.fish`. The same works for `portseal`, e.g. `alias pz=portseal`.

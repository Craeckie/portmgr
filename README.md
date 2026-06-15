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
  R   Rotate postgres/mariadb passwords and write new values to .env
```

You combine multiple commands. For example `portmgr dul`, runs docker compose with `down`, `up` and `logs`, thus stopping, removing and starting all containers and then showing the logs.

### Installation
```
sudo pip install portmgr
```

Or build it from source (here using the latest commit on master branch)
```
sudo pip install https://github.com/Craeckie/portmgr.git
```

### Sealing secrets

portmgr can encrypt secret-bearing files (`.env`, config files) with [age](https://age-encryption.org/) so they are safe to commit to git. Decryption happens once at setup time; the plaintext files remain on disk for Docker to use normally.

**Requires the `secrets` extra:**
```
pip install portmgr[secrets]
```

**Seal a file** (run inside a service directory):
```
portmgr E .env
```
This creates `.env.age`, adds `.env` to the local `.gitignore`, and writes a `.migrated` marker. Commit the `.age` file and `.migrated`; never commit the plaintext.

**Decrypt on a new server** (run from any ancestor directory):
```
portmgr D
```
Recurses via `dckrsub.yml` and decrypts every `*.age` whose plaintext is missing. Pass `--force` to overwrite existing plaintext from the sealed copy.

**Check migration progress:**
```
portmgr S
```
Reports `DONE`, `PENDING`, `INCONSISTENT`, or `CLEAN` for each service and prints a summary tally.

**Rotate database passwords:**
```
portmgr R
```
Finds postgres and mariadb services in each compose stack, generates a new random password, runs `ALTER USER` in the running container, and writes the new value(s) to `.env`. If a password was previously hardcoded in the compose file rather than referenced via `${VAR}`, a warning is printed reminding you to update the compose file to use the variable reference.

**Passphrase:** portmgr prompts once and caches the passphrase for the rest of the run. For non-interactive use (e.g. in scripts or provisioning), set:
```
PORTMGR_PASSPHRASE=<passphrase> portmgr D
```

After running `portmgr u`, a footer line is printed if any services have not yet been sealed.

### Tipps
If you use portmgr a lot like me, you might want to shorten it to one letter. For bash, you can add `alias p='portmgr'` to `~/.bashrc`. For fish-shell you can add `abbr p portmgr` to `~/.config/fish/config.fish`.

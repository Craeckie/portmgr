# Sealing secrets to per-host keys

portmgr seals secret files (`.env`, config files) with [age](https://age-encryption.org/) so they can be committed to git. There are two ways to seal:

- **Per-host keys:** a `seal-recipients.yml` in the repository lists each host's public key. Each file is sealed only to the hosts that run it, plus a recovery key. A host can unseal its own files and nothing else.
- **Shared passphrase:** used when no `seal-recipients.yml` exists. Every file is sealed with one passphrase (`PORTMGR_PASSPHRASE`), so every host that has it can read every file.

Both kinds of file can sit side by side. portmgr reads the file's header to see how it was sealed, so files you haven't moved to per-host keys keep working.

Everything here needs the `secrets` extra: `pip install portmgr[secrets]`.

## Commands

`portseal` works on files, wherever they are:

| Command | What it does |
|---|---|
| `portseal e <file>…` | Seal each file to `<file>.age` |
| `portseal d [--force] [path…]` | Unseal every `*.age` below the paths (default `.`) whose plaintext is missing; `--force` overwrites existing plaintext. Files that weren't sealed for this host are skipped and counted |
| `portseal k [--all] [path…]` | Reseal files whose recipients no longer match `seal-recipients.yml`, without writing plaintext; `--all` reseals every file |
| `portseal s [path…]` | Show who can unseal each file; exits 1 unless every file is `OK` |

Inside a compose tree, `portmgr E <file>` and `portmgr D` do the same as `portseal e` and `portseal d` for each stack. `portmgr D` unseals the files in each stack's directory and below it, such as `config/settings.yml.age`, and skips files not sealed for this host. Files outside any stack, such as a shared `_includes/` directory, are reached with `portseal d` from the top of the tree.

To shorten it in the shell, add `alias pz=portseal` to `~/.bashrc`, or `abbr pz portseal` to `~/.config/fish/config.fish`.

## The recipients file

`portseal` looks for `seal-recipients.yml` in the file's directory, then in each parent directory, and uses the first one it finds. Commit it: it holds only public keys.

```yaml
recovery:
  - age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqs3290gq

hosts:
  web:
    key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... user@web
  db:
    key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... user@db

rules:
  - path: secrets-web.sh
    hosts: [web]
  - path: shared/*
    hosts: [web, db]
```

- **`recovery`:** public keys that every file is sealed to, in addition to its hosts. At least one is required, so no file is ever sealed to host keys only; without one, `portseal` refuses to seal.
- **`hosts`:** each host's public key, either an SSH key (`ssh-ed25519 …`, `ssh-rsa …`) or an age key (`age1…`).
- **`rules`:** glob patterns matched against the plaintext file's path relative to the recipients file's directory. `*` also matches `/`. The first matching rule decides the hosts.

A file that no rule (and no dckrsub chain, below) matches is not sealed, and `portseal` says which file needs a rule.

### Hosts from dckrsub chains

In a tree where each host follows its own `dckrsub-<host>.yml` (see *One tree for several hosts* in the README), the hosts can be worked out from the chains instead of listing rules:

```yaml
recovery:
  - age1...
hosts:
  web:
    key: ssh-ed25519 AAAA... user@web
    sub: dckrsub-web.yml
  db:
    key: ssh-ed25519 AAAA... user@db
    sub: dckrsub-db.yml
```

For each host with a `sub`, portmgr follows that file plus `dckrsub.yml` from the recipients file's directory, the same way `PORTMGR_SUB_NAME=<sub> portmgr` would. A file goes to every host whose chain reaches the file's directory. If no chain reaches that directory itself, the nearest parent directory that a chain does reach decides. So `app/config/settings.yml` goes with the stack `app/`, and `group/_includes/.env` goes to the hosts that run `group/`. The top directory, which every chain starts in, never counts. Rules are checked first, so a rule can override the chains for single files.

## Host keys

`portseal` unseals with the private keys listed in `PORTMGR_IDENTITY` (comma-separated paths). If it isn't set, `~/.ssh/id_ed25519` is used. That is the user's own SSH key, so there is nothing extra to deploy: the private key is created on the host and never leaves it, and its public half goes into `hosts`.

- Every host needs its **own** key. Compare `ssh-keygen -lf ~/.ssh/id_ed25519.pub` across hosts before adding them; a key that was copied between hosts makes them indistinguishable.
- SSH keys must have no passphrase; age can't use passphrase-protected SSH keys.
- If a host's key is ever regenerated, put the new public key in `hosts` and run `portseal k` from a machine that can still unseal the files (for example with the recovery key).

## The recovery key

The recovery key unseals every file. You need it when a host loses its key (a reinstall or a regenerated key), and it's also the key for editing secrets on a machine that isn't one of the hosts.

1. Create it on a trusted machine: `age-keygen -o recovery.txt`. The line `# public key: age1…` is what goes into `recovery`.
2. Keep the private key off every server: in your password manager, plus an offline copy (paper or a USB stick).
3. Optionally protect the key file with a passphrase: `age -p -o recovery.txt.age recovery.txt`, then delete `recovery.txt`. `portseal` asks for the passphrase when `PORTMGR_IDENTITY` points to `recovery.txt.age`.
4. Test it once, in a fresh clone of the repository: `PORTMGR_IDENTITY=recovery.txt.age portseal d`.

The recovery key's public half isn't secret, but its integrity matters: whoever can swap it gets every file sealed afterwards. Change `seal-recipients.yml` through reviewed commits.

## Adding or removing a host

1. Add or remove its entry under `hosts` (and in `rules`, or add its `dckrsub-<host>.yml`).
2. Run `portseal k` on a machine that can unseal the affected files (the recovery key can unseal all of them).
3. Commit `seal-recipients.yml` and the resealed files together.

`portseal k` only rewrites files whose recipients changed, so the commit shows exactly which files a host gained or lost.

Removing a host stops it from unsealing **new versions** of files. Anything it could read before is in its git history and on its disk, so rotate those secrets if the host is no longer trusted.

## Moving from a passphrase

1. Create the recovery key, collect the host keys and write `seal-recipients.yml`.
2. `portseal s` lists every file as `PASSPHRASE` together with the hosts it should go to. Fix any file it can't place (`UNKNOWN`) with a rule.
3. `PORTMGR_PASSPHRASE=… portseal k` reseals everything; nothing is written in plaintext.
4. `portseal s` should now show every file as `OK`. Commit.

## What `portseal s` shows

```
  OK          app/.env.age  [web, recovery]
  STALE       shared/token.age  [web, recovery]  -> should be [web, db, recovery]
  PASSPHRASE  old/.env.age  -> should be [db, recovery]
  UNKNOWN     stray/.env.age  (no host for stray/.env: add a rule to …/seal-recipients.yml)
```

- `OK`: sealed to exactly the hosts and recovery keys it should be.
- `STALE`: the recipients differ from `seal-recipients.yml`; run `portseal k`.
- `PASSPHRASE`: still sealed with the shared passphrase.
- `UNKNOWN`: no recipients file, or no rule or chain for the file.

The host names come from the file itself. An SSH stanza in an age header carries a short tag of its key, which is matched against `hosts`; an unknown tag shows as `?<tag>`. Age-key (`age1…`) stanzas carry no name, so they're only counted. If the count equals the number of age keys the file should have, they're shown by those names, otherwise as `N x25519`.

## What a compromised host leaks

A host can unseal every file sealed to its key, and those plaintexts are already on its disk anyway. What per-host keys add is that it can't unseal the files of stacks it doesn't run. Files shared by several hosts are exposed by any one of them, and the recovery key unlocks everything, which is why it stays off the servers.

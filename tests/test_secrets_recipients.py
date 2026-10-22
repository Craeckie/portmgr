import os
import shutil
import subprocess

import pytest
import yaml

pyrage = pytest.importorskip("pyrage")

from portmgr import sealing, secrets  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    sealing._clear_passphrase()
    sealing._clear_identities()
    monkeypatch.delenv("PORTMGR_PASSPHRASE", raising=False)
    yield
    sealing._clear_identities()


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    directory = tmp_path_factory.mktemp("keys")
    result = {}
    for host in ("alpha", "beta"):
        path = directory / host
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
        result[host] = {"private": str(path), "public": (directory / f"{host}.pub").read_text().strip()}
    result["recovery"] = str(pyrage.x25519.Identity.generate().to_public())
    return result


def leaf(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "docker-compose.yml").write_text("services: {}\n")


def subs(path, name, entries):
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text("".join(f"- {e}\n" for e in entries))


@pytest.fixture
def tree(tmp_path, keys):
    """alpha runs awire/ and tools/, beta runs tools/; both run common/beszel, only
    beta runs common/beta-only."""
    subs(tmp_path, "dckrsub.yml", ["common"])
    subs(tmp_path, "dckrsub-alpha.yml", ["awire", "tools"])
    subs(tmp_path, "dckrsub-beta.yml", ["tools"])
    subs(tmp_path / "common", "dckrsub.yml", ["beszel"])
    subs(tmp_path / "common", "dckrsub-beta.yml", ["beta-only"])
    leaf(tmp_path / "common" / "beszel")
    leaf(tmp_path / "common" / "beta-only")
    subs(tmp_path / "awire", "dckrsub.yml", ["app"])
    leaf(tmp_path / "awire" / "app")
    (tmp_path / "awire" / "app" / "config").mkdir()
    (tmp_path / "awire" / "_includes").mkdir()
    subs(tmp_path / "tools", "dckrsub.yml", ["blog"])
    leaf(tmp_path / "tools" / "blog")
    (tmp_path / "stray").mkdir()
    doc = {
        "recovery": [keys["recovery"]],
        "hosts": {h: {"key": keys[h]["public"], "sub": f"dckrsub-{h}.yml"} for h in ("alpha", "beta")},
    }
    (tmp_path / sealing.RECIPIENTS_NAME).write_text(yaml.safe_dump(doc))
    return tmp_path


def resolve(tree, relative):
    config = sealing.load_recipients(str(tree / sealing.RECIPIENTS_NAME))
    return sorted(secrets.dckrsub_resolver(str(tree / relative), str(tree), config))


@pytest.mark.parametrize("relative, hosts", [
    ("common/beszel/.env", ["alpha", "beta"]),
    ("common/beta-only/.env", ["beta"]),
    ("awire/app/.env", ["alpha"]),
    ("awire/app/config/settings.yml", ["alpha"]),
    ("awire/_includes/.env", ["alpha"]),
    ("tools/blog/.env", ["alpha", "beta"]),
    ("stray/.env", []),
    (".env", []),
])
def test_resolver_maps_paths_to_hosts(tree, relative, hosts):
    assert resolve(tree, relative) == hosts


def test_host_without_sub_is_ignored(tree, keys):
    config = sealing.load_recipients(str(tree / sealing.RECIPIENTS_NAME))
    del config["hosts"]["beta"]["sub"]
    assert secrets.dckrsub_resolver(str(tree / "tools/blog/.env"), str(tree), config) == ["alpha"]


def test_seal_uses_dckrsub_and_writes_migrated(tree, keys, monkeypatch):
    secret = tree / "common" / "beta-only" / ".env"
    secret.write_text("PW=1\n")
    secrets.seal(str(secret))
    assert (secret.parent / ".migrated").is_file()

    info = sealing.status(str(secret) + ".age", resolver=secrets.dckrsub_resolver)
    assert info["hosts"] == ["beta", "recovery"]
    assert info["state"] == "OK"

    secret.unlink()
    monkeypatch.setenv("PORTMGR_IDENTITY", keys["alpha"]["private"])
    with pytest.raises(sealing.NotForThisHost):
        secrets.unseal(str(secret) + ".age")
    sealing._clear_identities()
    monkeypatch.setenv("PORTMGR_IDENTITY", keys["beta"]["private"])
    assert secrets.unseal(str(secret) + ".age") == "decrypted"


def test_seal_refuses_path_no_host_runs(tree):
    secret = tree / "stray" / ".env"
    secret.write_text("x")
    with pytest.raises(sealing.SealError, match="no host"):
        secrets.seal(str(secret))
    assert not os.path.exists(str(secret) + ".age")

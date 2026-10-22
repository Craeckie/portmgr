import os
import shutil
import subprocess
import sys

import pytest
import yaml

pyrage = pytest.importorskip("pyrage")

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


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


def portseal(args, cwd, identity=None, passphrase=None):
    env = dict(os.environ)
    env.pop("PORTMGR_PASSPHRASE", None)
    env["PORTMGR_IDENTITY"] = identity or "/nonexistent"
    if passphrase:
        env["PORTMGR_PASSPHRASE"] = passphrase
    return subprocess.run(
        [sys.executable, "-m", "portmgr.portseal", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def repo(tmp_path, keys):
    (tmp_path / "configs").mkdir()
    doc = {
        "recovery": [keys["recovery"]],
        "hosts": {h: {"key": keys[h]["public"]} for h in ("alpha", "beta")},
        "rules": [
            {"path": "configs/secrets-alpha.sh", "hosts": ["alpha"]},
            {"path": "configs/secrets-beta.sh", "hosts": ["beta"]},
        ],
    }
    (tmp_path / "seal-recipients.yml").write_text(yaml.safe_dump(doc))
    for host in ("alpha", "beta"):
        (tmp_path / "configs" / f"secrets-{host}.sh").write_text(f"PW={host}\n")
    return tmp_path


def test_no_args_prints_usage(tmp_path):
    result = portseal([], tmp_path)
    assert result.returncode == 2
    assert "usage" in (result.stdout + result.stderr).lower()


def test_seal_status_unseal(repo, keys):
    sealed = portseal(["e", "configs/secrets-alpha.sh", "configs/secrets-beta.sh"], repo)
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    for host in ("alpha", "beta"):
        (repo / "configs" / f"secrets-{host}.sh").unlink()

    status = portseal(["s"], repo)
    assert status.returncode == 0, status.stdout + status.stderr
    assert "OK" in status.stdout
    assert "configs/secrets-alpha.sh.age  [alpha, recovery]" in status.stdout

    # alpha unseals its own file and skips beta's without failing.
    unsealed = portseal(["d"], repo, identity=keys["alpha"]["private"])
    assert unsealed.returncode == 0, unsealed.stdout + unsealed.stderr
    assert (repo / "configs" / "secrets-alpha.sh").read_text() == "PW=alpha\n"
    assert not (repo / "configs" / "secrets-beta.sh").exists()
    assert "not sealed for this host" in unsealed.stdout


def test_rekey_from_passphrase(repo, keys):
    plain = repo / "configs" / "secrets-alpha.sh"
    (repo / "configs" / "secrets-alpha.sh.age").write_bytes(pyrage.passphrase.encrypt(plain.read_bytes(), "pw"))
    plain.unlink()

    before = portseal(["s", "configs"], repo)
    assert "PASSPHRASE" in before.stdout

    rekeyed = portseal(["k", "configs"], repo, passphrase="pw")
    assert rekeyed.returncode == 0, rekeyed.stdout + rekeyed.stderr
    assert not plain.exists()

    unsealed = portseal(["d", "configs"], repo, identity=keys["alpha"]["private"])
    assert unsealed.returncode == 0, unsealed.stdout + unsealed.stderr
    assert plain.read_text() == "PW=alpha\n"


def test_seal_without_rule_fails(repo):
    (repo / "configs" / "other.sh").write_text("x")
    result = portseal(["e", "configs/other.sh"], repo)
    assert result.returncode == 1
    assert "no host" in result.stdout
    assert not (repo / "configs" / "other.sh.age").exists()


def test_seal_in_stack_writes_migrated(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / ".env").write_text("PW=1\n")
    result = portseal(["e", ".env"], tmp_path, passphrase="pw")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / ".env.age").is_file()
    assert (tmp_path / ".migrated").is_file()


def test_missing_path_is_an_error(tmp_path):
    result = portseal(["d", "nope"], tmp_path)
    assert result.returncode == 1
    assert "nope: no such file or directory" in result.stdout

import shutil
import subprocess

import pytest
import yaml

pyrage = pytest.importorskip("pyrage")

from portmgr import sealing  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    sealing._clear_passphrase()
    sealing._clear_identities()
    monkeypatch.delenv("PORTMGR_PASSPHRASE", raising=False)
    monkeypatch.delenv("PORTMGR_IDENTITY", raising=False)
    yield
    sealing._clear_passphrase()
    sealing._clear_identities()


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    """Two throwaway SSH host keys and one age recovery key."""
    directory = tmp_path_factory.mktemp("keys")
    result = {}
    for host in ("alpha", "beta"):
        path = directory / host
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
        result[host] = {"private": str(path), "public": (directory / f"{host}.pub").read_text().strip()}
    recovery = pyrage.x25519.Identity.generate()
    recovery_path = directory / "recovery.txt"
    recovery_path.write_text(f"# recovery\n{recovery}\n")
    result["recovery"] = {"private": str(recovery_path), "public": str(recovery.to_public())}
    return result


def write_recipients(directory, keys, rules=None, recovery=True, hosts=("alpha", "beta")):
    doc = {"hosts": {h: {"key": keys[h]["public"]} for h in hosts}}
    if recovery:
        doc["recovery"] = [keys["recovery"]["public"]]
    if rules is not None:
        doc["rules"] = rules
    (directory / sealing.RECIPIENTS_NAME).write_text(yaml.safe_dump(doc))


def use_identity(monkeypatch, *paths):
    sealing._clear_identities()
    monkeypatch.setenv("PORTMGR_IDENTITY", ",".join(paths))


def test_seal_to_rule_hosts_plus_recovery(tmp_path, keys, monkeypatch):
    write_recipients(tmp_path, keys, rules=[{"path": "a/*", "hosts": ["alpha"]}])
    (tmp_path / "a").mkdir()
    secret = tmp_path / "a" / ".env"
    secret.write_text("PW=1\n")

    age_path = sealing.seal(str(secret))
    secret.unlink()

    use_identity(monkeypatch, keys["beta"]["private"])
    with pytest.raises(sealing.NotForThisHost):
        sealing.unseal(age_path)

    use_identity(monkeypatch, keys["alpha"]["private"])
    assert sealing.unseal(age_path) == "decrypted"
    assert secret.read_text() == "PW=1\n"

    secret.unlink()
    use_identity(monkeypatch, keys["recovery"]["private"])
    assert sealing.unseal(age_path) == "decrypted"


def test_first_matching_rule_wins(tmp_path, keys):
    write_recipients(tmp_path, keys, rules=[
        {"path": "secrets-alpha.sh", "hosts": ["alpha"]},
        {"path": "secrets-*.sh", "hosts": ["alpha", "beta"]},
    ])
    secret = tmp_path / "secrets-alpha.sh"
    secret.write_text("x")
    info = sealing.status(sealing.seal(str(secret)))
    assert info["hosts"] == ["alpha", "recovery"]
    assert info["state"] == "OK"


def test_seal_refused_without_recovery_key(tmp_path, keys):
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha"]}], recovery=False)
    secret = tmp_path / "s"
    secret.write_text("x")
    with pytest.raises(sealing.SealError, match="recovery"):
        sealing.seal(str(secret))
    assert not (tmp_path / "s.age").exists()


def test_seal_refused_without_matching_rule_or_resolver(tmp_path, keys):
    write_recipients(tmp_path, keys, rules=[{"path": "other", "hosts": ["alpha"]}])
    secret = tmp_path / "s"
    secret.write_text("x")
    with pytest.raises(sealing.SealError, match="no host"):
        sealing.seal(str(secret))
    with pytest.raises(sealing.SealError, match="no host"):
        sealing.seal(str(secret), resolver=lambda path, base, config: [])


def test_resolver_used_when_no_rule_matches(tmp_path, keys):
    write_recipients(tmp_path, keys)
    secret = tmp_path / "s"
    secret.write_text("x")
    seen = []

    def resolver(path, base, config):
        seen.append((path, base))
        return ["beta"]

    info = sealing.status(sealing.seal(str(secret), resolver=resolver), resolver=resolver)
    assert seen[0] == (str(secret), str(tmp_path))
    assert info["hosts"] == ["beta", "recovery"]
    assert info["state"] == "OK"


def test_unknown_host_in_rule_is_an_error(tmp_path, keys):
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["gamma"]}])
    secret = tmp_path / "s"
    secret.write_text("x")
    with pytest.raises(sealing.SealError, match="gamma"):
        sealing.seal(str(secret))


def test_no_recipients_file_seals_with_passphrase(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTMGR_PASSPHRASE", "pw")
    secret = tmp_path / "s"
    secret.write_text("x")
    age_path = sealing.seal(str(secret))
    assert sealing.status(age_path)["state"] == "PASSPHRASE"
    secret.unlink()
    assert sealing.unseal(age_path) == "decrypted"
    assert secret.read_text() == "x"


def test_old_scrypt_file_unseals_with_passphrase(tmp_path, keys, monkeypatch):
    # A recipients file appearing later doesn't stop old passphrase files from unsealing.
    monkeypatch.setenv("PORTMGR_PASSPHRASE", "pw")
    (tmp_path / "s.age").write_bytes(pyrage.passphrase.encrypt(b"old", "pw"))
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha"]}])
    assert sealing.unseal(str(tmp_path / "s.age")) == "decrypted"
    assert (tmp_path / "s").read_bytes() == b"old"


def test_rekey_turns_passphrase_into_recipients(tmp_path, keys, monkeypatch):
    monkeypatch.setenv("PORTMGR_PASSPHRASE", "pw")
    age_path = tmp_path / "s.age"
    age_path.write_bytes(pyrage.passphrase.encrypt(b"old", "pw"))
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha", "beta"]}])

    assert sealing.rekey(str(age_path)) == "rekeyed"
    assert not (tmp_path / "s").exists()  # no plaintext written
    info = sealing.status(str(age_path))
    assert info["state"] == "OK"
    assert info["hosts"] == ["alpha", "beta", "recovery"]

    # Already current: untouched unless forced.
    before = age_path.read_bytes()
    use_identity(monkeypatch, keys["beta"]["private"])
    assert sealing.rekey(str(age_path)) == "current"
    assert age_path.read_bytes() == before
    assert sealing.rekey(str(age_path), force=True) == "rekeyed"
    assert age_path.read_bytes() != before

    assert sealing.unseal(str(age_path)) == "decrypted"
    assert (tmp_path / "s").read_bytes() == b"old"


def test_status_reports_stale_after_host_removed(tmp_path, keys, monkeypatch):
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha", "beta"]}])
    secret = tmp_path / "s"
    secret.write_text("x")
    age_path = sealing.seal(str(secret))

    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha"]}])
    info = sealing.status(age_path)
    assert info["state"] == "STALE"
    assert info["hosts"] == ["alpha", "beta", "recovery"]
    assert info["expected"] == ["alpha", "recovery"]

    use_identity(monkeypatch, keys["alpha"]["private"])
    assert sealing.rekey(age_path) == "rekeyed"
    assert sealing.status(age_path)["hosts"] == ["alpha", "recovery"]


def test_status_names_unknown_ssh_tags(tmp_path, keys):
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha"]}], hosts=("alpha",))
    beta = pyrage.ssh.Recipient.from_str(keys["beta"]["public"])
    (tmp_path / "s.age").write_bytes(pyrage.encrypt(b"x", [beta]))
    info = sealing.status(str(tmp_path / "s.age"))
    assert info["hosts"] == ["?" + sealing.ssh_tag(keys["beta"]["public"])]
    assert info["state"] == "STALE"


def test_passphrase_protected_identity(tmp_path, keys, monkeypatch):
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha"]}])
    secret = tmp_path / "s"
    secret.write_text("x")
    age_path = sealing.seal(str(secret))
    secret.unlink()

    protected = tmp_path / "recovery.age"
    with open(keys["recovery"]["private"], "rb") as fh:
        protected.write_bytes(pyrage.passphrase.encrypt(fh.read(), "key-pw"))
    monkeypatch.setattr(sealing, "_ask", lambda prompt: "key-pw")
    use_identity(monkeypatch, str(protected))
    assert sealing.unseal(age_path) == "decrypted"


def test_missing_named_identity_is_an_error(tmp_path, keys, monkeypatch):
    write_recipients(tmp_path, keys, rules=[{"path": "*", "hosts": ["alpha"]}])
    secret = tmp_path / "s"
    secret.write_text("x")
    age_path = sealing.seal(str(secret))
    secret.unlink()
    use_identity(monkeypatch, str(tmp_path / "nope"))
    with pytest.raises(sealing.SealError, match="nope"):
        sealing.unseal(age_path)


def test_ssh_tag_matches_header(keys):
    rec = pyrage.ssh.Recipient.from_str(keys["alpha"]["public"])
    header = pyrage.encrypt(b"x", [rec]).split(b"\n---")[0].decode()
    assert f"-> ssh-ed25519 {sealing.ssh_tag(keys['alpha']['public'])} " in header


def test_find_age_files_walks_dirs_and_skips_git(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    for p in ("a/.env.age", "a/b/c.age", ".git/x.age", "a/plain"):
        (tmp_path / p).write_text("")
    found = sealing.find_age_files([str(tmp_path)])
    assert found == [str(tmp_path / "a" / ".env.age"), str(tmp_path / "a" / "b" / "c.age")]

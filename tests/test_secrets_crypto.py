import pytest

from portmgr import secrets

pytest.importorskip("pyrage")


@pytest.fixture(autouse=True)
def passphrase_env(monkeypatch):
    secrets._clear_passphrase()
    monkeypatch.setenv("PORTMGR_PASSPHRASE", "correct horse battery staple")
    yield
    secrets._clear_passphrase()


def test_seal_creates_artifacts(tmp_path):
    secret = tmp_path / "secret.env"
    secret.write_text("DB_PASSWORD=hunter2\n")

    secrets.seal(str(secret))

    assert (tmp_path / "secret.env.age").is_file()
    assert "secret.env" in (tmp_path / ".gitignore").read_text()
    assert (tmp_path / ".migrated").is_file()


def test_seal_then_unseal_round_trip(tmp_path):
    secret = tmp_path / "secret.env"
    original = "DB_PASSWORD=hunter2\nAPI_TOKEN=abc123\n"
    secret.write_text(original)

    secrets.seal(str(secret))
    secret.unlink()  # remove plaintext so unseal recreates it

    result = secrets.unseal(str(tmp_path / "secret.env.age"))
    assert result == "decrypted"
    assert secret.read_text() == original


def test_unseal_skips_when_target_exists(tmp_path):
    secret = tmp_path / "secret.env"
    secret.write_text("data\n")
    secrets.seal(str(secret))

    # plaintext still present -> skipped
    assert secrets.unseal(str(tmp_path / "secret.env.age")) == "skipped"


def test_unseal_force_overwrites(tmp_path):
    secret = tmp_path / "secret.env"
    secret.write_text("original\n")
    secrets.seal(str(secret))
    secret.write_text("tampered\n")

    assert secrets.unseal(str(tmp_path / "secret.env.age"), force=True) == "decrypted"
    assert secret.read_text() == "original\n"


def test_unseal_rejects_non_age_path(tmp_path):
    plain = tmp_path / "secret.env"
    plain.write_text("data\n")
    with pytest.raises(ValueError):
        secrets.unseal(str(plain))


def test_unseal_wrong_passphrase_from_env_raises(tmp_path, monkeypatch):
    secret = tmp_path / "secret.env"
    secret.write_text("data\n")
    secrets.seal(str(secret))
    secret.unlink()

    secrets._clear_passphrase()
    monkeypatch.setenv("PORTMGR_PASSPHRASE", "wrong-passphrase")
    with pytest.raises(ValueError):
        secrets.unseal(str(tmp_path / "secret.env.age"))

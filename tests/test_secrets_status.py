import textwrap

import pytest

from portmgr import secrets


@pytest.fixture(autouse=True)
def clear_passphrase_cache():
    secrets._clear_passphrase()
    yield
    secrets._clear_passphrase()


def compose_with_secret(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""
        services:
          web:
            environment:
              DB_PASSWORD: hunter2
    """))


def compose_without_secret(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(textwrap.dedent("""
        services:
          web:
            image: nginx
    """))


# --- service_status: the four states -------------------------------------

def test_status_done(tmp_path):
    compose_without_secret(tmp_path)
    secrets.write_migrated(str(tmp_path))
    state, keys = secrets.service_status(str(tmp_path))
    assert state == "DONE"
    assert keys == []


def test_status_inconsistent(tmp_path):
    compose_with_secret(tmp_path)
    secrets.write_migrated(str(tmp_path))
    state, keys = secrets.service_status(str(tmp_path))
    assert state == "INCONSISTENT"
    assert keys == [("web", "DB_PASSWORD")]


def test_status_pending(tmp_path):
    compose_with_secret(tmp_path)
    state, keys = secrets.service_status(str(tmp_path))
    assert state == "PENDING"
    assert keys == [("web", "DB_PASSWORD")]


def test_status_clean(tmp_path):
    compose_without_secret(tmp_path)
    state, keys = secrets.service_status(str(tmp_path))
    assert state == "CLEAN"
    assert keys == []


# --- gitignore_append ----------------------------------------------------

def test_gitignore_append_creates_file(tmp_path):
    secrets.gitignore_append(str(tmp_path), "secret.env")
    assert (tmp_path / ".gitignore").read_text() == "secret.env\n"


def test_gitignore_append_idempotent(tmp_path):
    secrets.gitignore_append(str(tmp_path), "secret.env")
    secrets.gitignore_append(str(tmp_path), "secret.env")
    assert (tmp_path / ".gitignore").read_text() == "secret.env\n"


def test_gitignore_append_inserts_missing_newline(tmp_path):
    (tmp_path / ".gitignore").write_text("existing")  # no trailing newline
    secrets.gitignore_append(str(tmp_path), "secret.env")
    assert (tmp_path / ".gitignore").read_text() == "existing\nsecret.env\n"


# --- write_migrated ------------------------------------------------------

def test_write_migrated_writes_iso_timestamp(tmp_path):
    from datetime import datetime

    secrets.write_migrated(str(tmp_path))
    content = (tmp_path / ".migrated").read_text().strip()
    # Parses back as an ISO timestamp without raising.
    datetime.fromisoformat(content)


# --- get_passphrase ------------------------------------------------------

def test_get_passphrase_from_cache():
    secrets._cache_passphrase("cached-pw")
    assert secrets.get_passphrase() == ("cached-pw", "cache")


def test_get_passphrase_from_env(monkeypatch):
    monkeypatch.setenv("PORTMGR_PASSPHRASE", "env-pw")
    assert secrets.get_passphrase() == ("env-pw", "env")

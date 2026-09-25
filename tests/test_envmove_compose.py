"""End-to-end: `portmgr M` must not change what compose hands the containers.

Needs a compose binary (`docker compose`, or a standalone `docker-compose`, or
one named in PORTMGR_TEST_COMPOSE); `config` needs no daemon.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest


def _compose_cmd():
    explicit = os.environ.get("PORTMGR_TEST_COMPOSE")
    if explicit:
        return [explicit]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    if shutil.which("docker"):
        probe = subprocess.run(["docker", "compose", "version"], capture_output=True)
        if probe.returncode == 0:
            return ["docker", "compose"]
    return None


COMPOSE = _compose_cmd()
pytestmark = pytest.mark.skipif(COMPOSE is None, reason="no docker compose binary")

FIXTURE = textwrap.dedent(r"""
    x-shared: &shared
      SHARED_TOKEN: shared-secret
    services:
      db:
        image: postgres  # comment stays
        environment:
          POSTGRES_PASSWORD: pa$$word
          SPACED_SECRET: 'with space'
          QUOTE_SECRET: "it's \"quoted\""
          BACKSLASH_SECRET: 'back\slash'
          HASH_SECRET: 'hash # inside'
          UNICODE_SECRET: ünïcødé
          PORT: 5432
          ENABLED: true
          RATIO: 0.5
          ZIP: '007'
          HOME: /srv/db
          VERSION: 1.2.3
          REF: ${ALREADY}
      app:
        image: app
        environment:
          - POSTGRES_PASSWORD=other
          - "LIST_SECRET=list value $$x"
          - PLAIN=abc
      flow:
        image: flow
        environment: {FLOW_KEY: fl0w, FLOW_OTHER: keep}
      a1:
        image: a
        environment: *shared
      a2:
        image: a
        environment: *shared
""").lstrip()


def compose_config(cwd):
    result = subprocess.run([*COMPOSE, "config", "--format", "json"], cwd=cwd,
                            capture_output=True, text=True,
                            env={**os.environ, "ALREADY": "from-shell"})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def run_move(cwd, answers):
    return subprocess.run([sys.executable, "-m", "portmgr", "M"], cwd=cwd, input=answers,
                          capture_output=True, text=True)


def test_move_all_keeps_resolved_config(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(FIXTURE)
    (tmp_path / ".env").write_text("EXISTING=1")  # no trailing newline
    before = compose_config(tmp_path)

    result = run_move(tmp_path, "a\ny\n")
    assert result.returncode == 0, result.stdout + result.stderr

    after = compose_config(tmp_path)
    assert after == before
    compose_text = (tmp_path / "docker-compose.yml").read_text()
    assert "# comment stays" in compose_text
    assert "pa$$word" not in compose_text and "shared-secret" not in compose_text
    dotenv = (tmp_path / ".env").read_text()
    assert dotenv.startswith("EXISTING=1\nPOSTGRES_PASSWORD='pa$word'\n")
    # HOME is set in any shell and would win over .env, so it is renamed.
    assert "DB_HOME=/srv/db\n" in dotenv
    assert "APP_POSTGRES_PASSWORD=other\n" in dotenv

    # Everything movable is now a reference; a second run finds nothing.
    again = run_move(tmp_path, "")
    assert "nothing to move" in again.stdout


def test_default_selection_moves_only_secret_like_keys(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(FIXTURE)
    before = compose_config(tmp_path)

    result = run_move(tmp_path, "\ny\n")
    assert result.returncode == 0, result.stdout + result.stderr

    assert compose_config(tmp_path) == before
    dotenv = (tmp_path / ".env").read_text()
    assert "POSTGRES_PASSWORD=" in dotenv and "SHARED_TOKEN=" in dotenv
    assert "PORT=" not in dotenv and "PLAIN=" not in dotenv
    assert oct((tmp_path / ".env").stat().st_mode & 0o777) == "0o600"


def test_declining_writes_nothing(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(FIXTURE)
    result = run_move(tmp_path, "a\nn\n")
    assert result.returncode == 0
    assert (tmp_path / "docker-compose.yml").read_text() == FIXTURE
    assert not (tmp_path / ".env").exists()

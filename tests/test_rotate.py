"""`portmgr R` against a faked `docker compose` (config + exec)."""
import json
import subprocess

import pytest

from portmgr.commands import P


class FakeCompose:
    """Stands in for `docker compose config` and `docker compose exec`.

    `raw` is what `config --no-interpolate` returns, `resolved` what plain
    `config` returns. `handler(svc, cmd_args)` answers each exec with
    (returncode, stdout, stderr).
    """

    def __init__(self, monkeypatch, raw, resolved, handler):
        self.raw = raw
        self.resolved = resolved
        self.handler = handler
        self.execs = []
        monkeypatch.setattr(P, "check_output", self._check_output)
        monkeypatch.setattr(P, "run", self._run)

    def _check_output(self, args, **kwargs):
        services = self.raw if "--no-interpolate" in args else self.resolved
        return json.dumps({"services": services}).encode()

    def _run(self, args, **kwargs):
        assert args[:4] == ["docker", "compose", "exec", "-T"]
        svc, cmd_args = args[4], args[5:]
        self.execs.append((svc, cmd_args))
        rc, out, err = self.handler(svc, cmd_args)
        return subprocess.CompletedProcess(args, rc, out, err)

    def sql(self):
        """Every SQL string passed via -e/-c, in order."""
        return [c[c.index(flag) + 1] for _, c in self.execs
                for flag in ("-e", "-c") if flag in c]


def mysql_server(hosts=None, client="mysql", fail_on=None):
    """Handler for a mysql/mariadb container: only `client` exists."""
    hosts = hosts or {"root": ["localhost"], "intbooks": ["%"]}

    def handler(svc, cmd):
        if cmd[0] == "sh":
            return (0, f"/usr/bin/{client}\n", "") if client else (127, "", "")
        if cmd[0] != client:
            return 126, f'OCI runtime exec failed: "{cmd[0]}": executable file not found\n', ""
        sql = cmd[cmd.index("-e") + 1]
        if fail_on and fail_on in sql:
            return 1, "", "ERROR 1045 (28000): Access denied"
        if sql.startswith("SELECT Host"):
            user = sql.split("User=")[1].strip("';")
            return 0, "".join(h + "\n" for h in hosts.get(user, [])), ""
        return 0, "", ""
    return handler


INTBOOKS_RAW = {"mysql": {"image": "mysql/mysql-server", "environment": {
    "MYSQL_DATABASE": "intbooks",
    "MYSQL_USER": "intbooks",
    "MYSQL_PASSWORD": "${MYSQL_PASS}",
    "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASS}",
}}}
INTBOOKS_RESOLVED = {"mysql": {"image": "mysql/mysql-server", "environment": {
    "MYSQL_DATABASE": "intbooks",
    "MYSQL_USER": "intbooks",
    "MYSQL_PASSWORD": "oldapp",
    "MYSQL_ROOT_PASSWORD": "oldroot",
}}}


def rotate(tmp_path, dotenv=None):
    if dotenv is not None:
        (tmp_path / ".env").write_text(dotenv)
    rc = P.func({"directory": str(tmp_path), "relative": "intbooks/docker"})
    assert rc == 0
    env = tmp_path / ".env"
    return P._dotenv_read(str(env)) if env.exists() else None


def test_mysql_server_falls_back_to_mysql_client(tmp_path, monkeypatch):
    fake = FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED, mysql_server())
    rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    clients = {c[0] for _, c in fake.execs if c[0] != "sh"}
    assert clients == {"mysql"}
    assert any("ALTER USER 'root'@'localhost'" in s for s in fake.sql())


def test_no_client_in_container_is_reported_and_env_untouched(tmp_path, monkeypatch, capsys):
    FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED, mysql_server(client=None))
    env = rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    assert env == {"MYSQL_PASS": "oldapp", "MYSQL_ROOT_PASS": "oldroot"}
    assert "no mariadb/mysql client in container" in capsys.readouterr().out


def test_failed_exec_reports_exit_code_and_stdout(tmp_path, monkeypatch, capsys):
    def handler(svc, cmd):
        if cmd[0] == "sh":
            return 0, "/usr/bin/mariadb\n", ""
        return 126, "exec failed: something on stdout\n", ""
    FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED, handler)
    rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    out = capsys.readouterr().out
    assert "exit 126" in out
    assert "something on stdout" in out


def test_env_written_under_referenced_variable(tmp_path, monkeypatch):
    FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED, mysql_server())
    env = rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    assert set(env) == {"MYSQL_PASS", "MYSQL_ROOT_PASS"}
    assert env["MYSQL_PASS"] not in ("oldapp", "")
    assert env["MYSQL_ROOT_PASS"] not in ("oldroot", "")


def test_default_syntax_reference_resolves_to_its_name(tmp_path, monkeypatch):
    raw = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_ROOT_PASSWORD": "${ROOT_PW:-fallback}"}}}
    resolved = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_ROOT_PASSWORD": "fallback"}}}
    FakeCompose(monkeypatch, raw, resolved, mysql_server(client="mariadb"))
    env = rotate(tmp_path)
    assert set(env) == {"ROOT_PW"}


def test_list_form_raw_environment_resolves(tmp_path, monkeypatch):
    # `config --no-interpolate` keeps a list-form environment as K=V strings.
    raw = {"db": {"image": "mariadb:11", "environment": [
        "MARIADB_ROOT_PASSWORD=${ROOT_PW}", "MARIADB_AUTO_UPGRADE"]}}
    resolved = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_ROOT_PASSWORD": "old", "MARIADB_AUTO_UPGRADE": None}}}
    FakeCompose(monkeypatch, raw, resolved, mysql_server(client="mariadb"))
    env = rotate(tmp_path, "ROOT_PW=old\n")
    assert set(env) == {"ROOT_PW"}


def test_literal_value_written_under_container_key_with_note(tmp_path, monkeypatch, capsys):
    raw = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_ROOT_PASSWORD": "hunter2"}}}
    FakeCompose(monkeypatch, raw, raw, mysql_server(client="mariadb"))
    env = rotate(tmp_path)
    assert set(env) == {"MARIADB_ROOT_PASSWORD"}
    assert "NOTE" in capsys.readouterr().out


def test_mixed_value_is_not_rotated(tmp_path, monkeypatch, capsys):
    raw = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_ROOT_PASSWORD": "pre${X}"}}}
    resolved = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_ROOT_PASSWORD": "prex"}}}
    fake = FakeCompose(monkeypatch, raw, resolved, mysql_server(client="mariadb"))
    assert rotate(tmp_path) is None
    assert fake.execs == []
    assert "pre${X}" in capsys.readouterr().out


def test_every_host_of_the_account_is_altered(tmp_path, monkeypatch):
    hosts = {"root": ["%", "localhost"], "intbooks": ["%", "localhost"]}
    fake = FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED, mysql_server(hosts))
    rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    alters = [s for s in fake.sql() if s.startswith("ALTER USER")]
    assert len(alters) == 2
    assert "'root'@'%'" in alters[0] and "'root'@'localhost'" in alters[0]
    assert "'intbooks'@'%'" in alters[1] and "'intbooks'@'localhost'" in alters[1]


def test_old_and_new_passwords_are_printed(tmp_path, monkeypatch, capsys):
    FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED, mysql_server())
    env = rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    out = capsys.readouterr().out
    assert f"MYSQL_ROOT_PASS\n    old: oldroot\n    new: {env['MYSQL_ROOT_PASS']}\n" in out
    assert f"MYSQL_PASS\n    old: oldapp\n    new: {env['MYSQL_PASS']}\n" in out


def test_partial_success_prints_and_writes_the_root_change(tmp_path, monkeypatch, capsys):
    fake = FakeCompose(monkeypatch, INTBOOKS_RAW, INTBOOKS_RESOLVED,
                       mysql_server(fail_on="'intbooks'@"))
    env = rotate(tmp_path, "MYSQL_PASS=oldapp\nMYSQL_ROOT_PASS=oldroot\n")
    out = capsys.readouterr().out
    assert env["MYSQL_PASS"] == "oldapp"
    assert f"MYSQL_ROOT_PASS\n    old: oldroot\n    new: {env['MYSQL_ROOT_PASS']}\n" in out
    assert "Access denied" in out
    # The app-user step logs in with the new root password.
    app_step = [c for _, c in fake.execs if "'intbooks'@" in c[-1]][0]
    assert f"--password={env['MYSQL_ROOT_PASS']}" in app_step


def test_same_variable_for_root_and_app_gets_one_password(tmp_path, monkeypatch):
    raw = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_USER": "app",
        "MARIADB_PASSWORD": "${DB_PASS}",
        "MARIADB_ROOT_PASSWORD": "${DB_PASS}"}}}
    resolved = {"db": {"image": "mariadb:11", "environment": {
        "MARIADB_USER": "app",
        "MARIADB_PASSWORD": "same",
        "MARIADB_ROOT_PASSWORD": "same"}}}
    fake = FakeCompose(monkeypatch, raw, resolved,
                       mysql_server({"root": ["%"], "app": ["%"]}, client="mariadb"))
    env = rotate(tmp_path)
    new = env["DB_PASS"]
    alters = [s for s in fake.sql() if s.startswith("ALTER USER")]
    assert len(alters) == 2
    assert all(f"IDENTIFIED BY '{new}'" in s for s in alters)


@pytest.mark.parametrize("raw_pw", ["${DB_PASS}", "$DB_PASS"])
def test_postgres_resolves_name_and_prints_old_and_new(tmp_path, monkeypatch, capsys, raw_pw):
    raw = {"pg": {"image": "postgres:16", "environment": {
        "POSTGRES_USER": "app", "POSTGRES_PASSWORD": raw_pw}}}
    resolved = {"pg": {"image": "postgres:16", "environment": {
        "POSTGRES_USER": "app", "POSTGRES_PASSWORD": "oldpg"}}}
    fake = FakeCompose(monkeypatch, raw, resolved, lambda svc, cmd: (0, "ALTER ROLE\n", ""))
    env = rotate(tmp_path, "DB_PASS=oldpg\n")
    assert set(env) == {"DB_PASS"}
    assert f"DB_PASS\n    old: oldpg\n    new: {env['DB_PASS']}\n" in capsys.readouterr().out
    assert fake.execs[0][1][0] == "psql"

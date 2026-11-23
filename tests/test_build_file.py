"""`r` and `b` build from a file holding only the services' build sections.

A build host then needs nothing else the stack's compose file refers to: no
`.env`, no `extends` file, no variables used outside the build sections.
"""
import os
import shutil
import subprocess
import textwrap

import pytest
import yaml

from portmgr import wrapper
from portmgr.commands import build as build_cmd
from portmgr.commands import push as push_cmd

STACK = textwrap.dedent("""
    name: mystack
    x-build: &build
      context: ./worker
      dockerfile: Dockerfile.worker
    services:
      web:
        build:
          context: ./web
          additional_contexts:
            assets: ../assets
        image: registry.example/web:latest
        platform: linux/amd64
        environment:
          TOKEN: ${TOKEN:?TOKEN must be set}
        ports: !reset []
        depends_on: [db]
      worker:
        <<: {build: *build}
        image: registry.example/worker:${TAG:-latest}
        command: !override ["run"]
      db:
        extends:
          file: ../_includes/sealed.yml
          service: postgres
      debug:
        build: ./debug
        profiles: [debug]
      plain:
        image: nginx
""").lstrip()


@pytest.fixture
def stack(tmp_path, monkeypatch):
    directory = tmp_path / "mystack"
    directory.mkdir()
    (directory / "docker-compose.yml").write_text(STACK)
    for sub in ("web", "worker", "debug"):
        (directory / sub).mkdir()
        (directory / sub / "Dockerfile").write_text("FROM scratch\n")
    (directory / "worker" / "Dockerfile.worker").write_text("FROM scratch\n")
    (tmp_path / "assets").mkdir()
    monkeypatch.delenv("COMPOSE_PROFILES", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.delenv("PORTMGR_MULTI_PLATFORM", raising=False)
    monkeypatch.delenv("PORTMGR_CLEAN_AFTER_PUSH", raising=False)
    monkeypatch.chdir(directory)
    return directory


def test_finds_only_services_with_their_own_build(stack):
    services = wrapper.getBuildServices()
    assert set(services) == {"web", "worker"}
    assert services["web"] == {
        "build": {"context": "./web", "additional_contexts": {"assets": "../assets"}},
        "image": "registry.example/web:latest",
        "platform": "linux/amd64",
    }
    # merge key and anchor resolved, the variable left for compose to fill in
    assert services["worker"] == {
        "build": {"context": "./worker", "dockerfile": "Dockerfile.worker"},
        "image": "registry.example/worker:${TAG:-latest}",
    }


def test_profiled_service_only_when_its_profile_is_active(stack, monkeypatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "other,debug")
    assert set(wrapper.getBuildServices()) == {"web", "worker", "debug"}
    monkeypatch.setenv("COMPOSE_PROFILES", "*")
    assert "debug" in wrapper.getBuildServices()


def test_reset_on_a_build_key_drops_it(stack):
    (stack / "docker-compose.yml").write_text(
        "services:\n  a:\n    build: .\n    platform: !reset null\n")
    assert wrapper.getBuildServices() == {"a": {"build": "."}}


def test_empty_services_is_nothing_to_build(stack):
    (stack / "docker-compose.yml").write_text("services:\n")
    assert wrapper.getBuildServices() == {}


def test_unreadable_compose_file_gives_none(stack):
    (stack / "docker-compose.yml").write_text("services: [unclosed\n")
    assert wrapper.getBuildServices() is None
    (stack / "docker-compose.yml").write_text("- a list\n")
    assert wrapper.getBuildServices() is None
    os.remove(stack / "docker-compose.yml")
    assert wrapper.getBuildServices() is None


def test_build_file_written_and_removed(stack):
    with wrapper.buildFile() as (services, files):
        assert files == ["-f", wrapper.BUILD_FILE]
        assert set(services) == {"web", "worker"}
        written = yaml.safe_load((stack / wrapper.BUILD_FILE).read_text())
        assert written["name"] == "mystack"
        assert written["services"] == services
    assert not (stack / wrapper.BUILD_FILE).exists()


def test_build_file_removed_after_an_error(stack):
    with pytest.raises(RuntimeError):
        with wrapper.buildFile():
            assert (stack / wrapper.BUILD_FILE).exists()
            raise RuntimeError("build blew up")
    assert not (stack / wrapper.BUILD_FILE).exists()


def test_without_name_the_build_file_has_none(stack):
    (stack / "docker-compose.yml").write_text("services:\n  a:\n    build: .\n")
    with wrapper.buildFile():
        written = yaml.safe_load((stack / wrapper.BUILD_FILE).read_text())
    assert written == {"services": {"a": {"build": "."}}}


def test_fallback_to_compose_config_with_a_note(stack, monkeypatch, capsys):
    (stack / "docker-compose.yml").write_text("services: [unclosed\n")
    monkeypatch.setattr(wrapper, "getServices",
                        lambda includeOnlyBuildable=False: {"svc": {"build": "."}})
    with wrapper.buildFile() as (services, files):
        assert services == {"svc": {"build": "."}}
        assert files == []
    assert not (stack / wrapper.BUILD_FILE).exists()
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1
    assert "docker compose config" in out


class Recorder:
    def __init__(self, stack):
        self.stack = stack
        self.calls = []

    def __call__(self, args, **kwargs):
        # the build file must exist while compose/buildx reads it
        assert (self.stack / wrapper.BUILD_FILE).exists()
        self.calls.append(list(args))
        return 0


def test_r_builds_and_pushes_from_the_build_file(stack, monkeypatch):
    rec = Recorder(stack)
    monkeypatch.setattr(push_cmd, "runCompose", rec)
    assert push_cmd.func({"relative": "mystack"}) == 0
    f = ["-f", ".portmgr-build.yml"]
    assert rec.calls == [
        f + ["build", "--pull", "--force-rm", "--compress", "web"],
        f + ["push", "--ignore-missing", "web"],
        f + ["build", "--pull", "--force-rm", "--compress", "worker"],
        f + ["push", "--ignore-missing", "worker"],
    ]
    assert not (stack / wrapper.BUILD_FILE).exists()


def test_r_bake_uses_the_build_file(stack, monkeypatch):
    monkeypatch.setenv("PORTMGR_MULTI_PLATFORM", "linux/amd64,linux/arm64")
    rec = Recorder(stack)
    monkeypatch.setattr(push_cmd, "runBuildx", rec)
    assert push_cmd.func({"relative": "mystack"}) == 0
    assert rec.calls[0] == ["bake", "-f", ".portmgr-build.yml", "--pull", "--push",
                            "--set", "*.platform=linux/amd64,linux/arm64", "web"]
    assert [c[-1] for c in rec.calls] == ["web", "worker"]
    assert not (stack / wrapper.BUILD_FILE).exists()


def test_r_no_cache_reaches_compose_build_only(stack, monkeypatch):
    monkeypatch.setattr(push_cmd, "command_extra", ["--no-cache"])
    rec = Recorder(stack)
    monkeypatch.setattr(push_cmd, "runCompose", rec)
    assert push_cmd.func({"relative": "mystack"}) == 0
    f = ["-f", ".portmgr-build.yml"]
    assert rec.calls[0] == f + ["build", "--pull", "--no-cache", "--force-rm", "--compress", "web"]
    assert rec.calls[1] == f + ["push", "--ignore-missing", "web"]


def test_r_no_cache_reaches_bake(stack, monkeypatch):
    monkeypatch.setenv("PORTMGR_MULTI_PLATFORM", "linux/amd64")
    monkeypatch.setattr(push_cmd, "command_extra", ["--no-cache"])
    rec = Recorder(stack)
    monkeypatch.setattr(push_cmd, "runBuildx", rec)
    assert push_cmd.func({"relative": "mystack"}) == 0
    assert rec.calls[0] == ["bake", "-f", ".portmgr-build.yml", "--pull", "--no-cache", "--push",
                            "--set", "*.platform=linux/amd64", "web"]


def test_r_cleans_up_when_a_build_raises(stack, monkeypatch):
    def boom(args, **kwargs):
        raise OSError("docker not found")
    monkeypatch.setattr(push_cmd, "runCompose", boom)
    with pytest.raises(OSError):
        push_cmd.func({"relative": "mystack"})
    assert not (stack / wrapper.BUILD_FILE).exists()


def test_b_builds_from_the_build_file(stack, monkeypatch):
    rec = Recorder(stack)
    monkeypatch.setattr(build_cmd, "runCompose", lambda args, **kw: rec(args))
    assert build_cmd.func({"relative": "mystack"}) == 0
    assert rec.calls == [["-f", ".portmgr-build.yml", "build", "--pull"]]
    assert not (stack / wrapper.BUILD_FILE).exists()


def test_b_falls_back_to_the_plain_compose_file(stack, monkeypatch):
    (stack / "docker-compose.yml").write_text("services: [unclosed\n")
    monkeypatch.setattr(wrapper, "getServices", lambda includeOnlyBuildable=False: {})
    calls = []
    monkeypatch.setattr(build_cmd, "runCompose", lambda args, **kw: calls.append(args) or 0)
    assert build_cmd.func({"relative": "mystack"}) == 0
    assert calls == [["build", "--pull"]]


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


@pytest.mark.skipif(COMPOSE is None, reason="no docker compose binary")
def test_compose_accepts_the_build_file_where_the_full_file_fails(stack):
    env = {k: v for k, v in os.environ.items() if k not in ("TOKEN", "COMPOSE_PROFILES")}
    full = subprocess.run([*COMPOSE, "config", "-q"], capture_output=True, text=True, env=env)
    assert full.returncode != 0
    with wrapper.buildFile() as (_, files):
        result = subprocess.run([*COMPOSE, *files, "config", "--format", "json"],
                                capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    config = yaml.safe_load(result.stdout)
    assert config["name"] == "mystack"
    assert set(config["services"]) == {"web", "worker"}
    web = config["services"]["web"]["build"]
    assert web["context"] == str(stack / "web")
    assert web["additional_contexts"]["assets"] == str(stack.parent / "assets")


def test_build_file_keeps_the_secrets_its_builds_use(stack):
    (stack / "docker-compose.yml").write_text(textwrap.dedent("""
        services:
          a:
            build:
              context: https://git.example/repo.git#main
              secrets:
                - GIT_AUTH_TOKEN.git.example
            secrets: [runtime_key]
          b:
            build:
              context: .
              secrets:
                - source: npmrc
                  target: npm
          c:
            image: nginx
            secrets: [other]
        secrets:
          GIT_AUTH_TOKEN.git.example:
            file: ../_includes/gitea-token
          npmrc:
            environment: NPMRC
          runtime_key:
            file: ./runtime_key
          other:
            file: ./other
    """).lstrip())
    with wrapper.buildFile():
        written = yaml.safe_load((stack / wrapper.BUILD_FILE).read_text())
    assert written["secrets"] == {
        "GIT_AUTH_TOKEN.git.example": {"file": "../_includes/gitea-token"},
        "npmrc": {"environment": "NPMRC"},
    }
    assert "secrets" not in written["services"]["a"]


def test_build_file_without_build_secrets_has_no_secrets(stack):
    with wrapper.buildFile():
        written = yaml.safe_load((stack / wrapper.BUILD_FILE).read_text())
    assert "secrets" not in written


# --- build timeout: PORTMGR_BUILD_TIMEOUT and the per-service x-portmgr-build-timeout ---

TIMEOUT_STACK = textwrap.dedent("""
    services:
      slow:
        build: ./slow
        image: registry.example/slow
        x-portmgr-build-timeout: 60m
      fast:
        build: ./fast
        image: registry.example/fast
""").lstrip()


class TimeoutRecorder:
    """Records (args, timeout) of every call; raises TimeoutExpired for the named services."""
    def __init__(self, expire=()):
        self.calls = []
        self.expire = expire

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs.get("timeout")))
        if args[-1] in self.expire and kwargs.get("timeout"):
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return 0

    def builds(self):
        return {args[-1]: timeout for args, timeout in self.calls
                if "build" in args or "bake" in args}


@pytest.fixture
def timeout_stack(stack, monkeypatch):
    (stack / "docker-compose.yml").write_text(TIMEOUT_STACK)
    monkeypatch.delenv("PORTMGR_BUILD_TIMEOUT", raising=False)
    return stack


@pytest.mark.parametrize("value, seconds", [
    ("3600", 3600), (3600, 3600), ("90s", 90), ("60m", 3600), ("1h", 3600),
    ("1h30m", 5400), (" 2h ", 7200), ("1h0m30s", 3630),
])
def test_parse_duration(value, seconds):
    assert wrapper.parse_duration(value) == seconds


@pytest.mark.parametrize("value", ["", "0", "0m", "-5", "abc", "60x", "m", None, True, 1.5])
def test_parse_duration_rejects(value):
    assert wrapper.parse_duration(value) is None


def test_timeout_key_kept_for_r_but_not_written(timeout_stack):
    with wrapper.buildFile() as (services, _):
        assert services["slow"]["x-portmgr-build-timeout"] == "60m"
        written = yaml.safe_load((timeout_stack / wrapper.BUILD_FILE).read_text())
    assert written["services"]["slow"] == {"build": "./slow", "image": "registry.example/slow"}


def test_r_default_timeout_is_20_minutes_and_a_service_can_raise_it(timeout_stack, monkeypatch):
    rec = TimeoutRecorder()
    monkeypatch.setattr(push_cmd, "runCompose", rec)
    assert push_cmd.func({"relative": "s"}) == 0
    assert rec.builds() == {"slow": 3600, "fast": 1200}
    # the push isn't limited
    assert [t for args, t in rec.calls if "push" in args] == [None, None]


def test_r_env_sets_the_default_and_the_service_still_wins(timeout_stack, monkeypatch):
    monkeypatch.setenv("PORTMGR_BUILD_TIMEOUT", "90m")
    rec = TimeoutRecorder()
    monkeypatch.setattr(push_cmd, "runCompose", rec)
    push_cmd.func({"relative": "s"})
    assert rec.builds() == {"slow": 3600, "fast": 5400}


def test_r_bake_gets_the_timeout_too(timeout_stack, monkeypatch):
    monkeypatch.setenv("PORTMGR_MULTI_PLATFORM", "linux/arm64")
    rec = TimeoutRecorder()
    monkeypatch.setattr(push_cmd, "runBuildx", rec)
    push_cmd.func({"relative": "s"})
    assert rec.builds() == {"slow": 3600, "fast": 1200}


def test_r_invalid_timeout_warns_and_uses_the_default(timeout_stack, monkeypatch, capsys):
    (timeout_stack / "docker-compose.yml").write_text(
        TIMEOUT_STACK.replace("60m", "an hour"))
    monkeypatch.setenv("PORTMGR_BUILD_TIMEOUT", "soon")
    rec = TimeoutRecorder()
    monkeypatch.setattr(push_cmd, "runCompose", rec)
    push_cmd.func({"relative": "s"})
    assert rec.builds() == {"slow": 1200, "fast": 1200}
    out = capsys.readouterr().out
    assert "PORTMGR_BUILD_TIMEOUT" in out and "soon" in out
    assert "x-portmgr-build-timeout" in out and "an hour" in out


def test_r_timed_out_build_says_after_how_long_and_fails(timeout_stack, monkeypatch, capsys):
    rec = TimeoutRecorder(expire=("slow",))
    monkeypatch.setattr(push_cmd, "runCompose", rec)
    assert push_cmd.func({"relative": "s"}) != 0
    out = capsys.readouterr().out
    # Registry-Updater's report.py matches on "Build timed out"
    assert "Error building slow! Build timed out after 1h00m." in out
    # the next service is still built and pushed
    assert (["push", "--ignore-missing", "fast"], None) in [
        (args[-3:], t) for args, t in rec.calls]


def test_r_a_later_successful_service_keeps_the_stack_failed(stack, monkeypatch):
    def first_fails(args, **kwargs):
        return 1 if args[-2:] == ["--compress", "web"] else 0
    monkeypatch.setattr(push_cmd, "runCompose", first_fails)
    assert push_cmd.func({"relative": "mystack"}) == 1


def test_r_bake_timeout_fails_the_stack(timeout_stack, monkeypatch):
    monkeypatch.setenv("PORTMGR_MULTI_PLATFORM", "linux/arm64")
    monkeypatch.setattr(push_cmd, "runBuildx", TimeoutRecorder(expire=("slow",)))
    assert push_cmd.func({"relative": "s"}) != 0

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
        f + ["push", "--ignore-push-failures", "web"],
        f + ["build", "--pull", "--force-rm", "--compress", "worker"],
        f + ["push", "--ignore-push-failures", "worker"],
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

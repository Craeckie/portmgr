"""Unattended runs: output order, PORTMGR_LOG_DIR, PORTMGR_RESULTS, PORTMGR_STOP_FILE.

Each test runs the real CLI in a subprocess with a fake `docker` first on PATH,
so the subprocess output really shares portmgr's file descriptors.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

from portmgr import runlog

FAKE_DOCKER = textwrap.dedent("""\
    #!/bin/sh
    # Fake docker: says where it runs, on stdout and stderr; fails in a stack
    # named in FAKE_FAIL; creates FAKE_TOUCH while running in FAKE_TOUCH_IN.
    stack=$(basename "$PWD")
    echo "docker-out $stack $*"
    echo "docker-err $stack" >&2
    if [ -n "$FAKE_TOUCH_IN" ] && [ "$stack" = "$FAKE_TOUCH_IN" ]; then
        touch "$FAKE_TOUCH"
    fi
    case " $FAKE_FAIL " in
        *" $stack "*) exit 1 ;;
    esac
    exit 0
""")

COMPOSE = textwrap.dedent("""\
    services:
      app:
        build: .
        image: registry.example/{name}:${{TAG:-latest}}
      db:
        image: postgres
""")


@pytest.fixture
def tree(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)

    root = tmp_path / "tree"
    for name in ("alpha", "group/beta", "gamma"):
        stack = root / name
        stack.mkdir(parents=True)
        (stack / "docker-compose.yml").write_text(COMPOSE.format(name=os.path.basename(name)))
    (root / "dckrsub.yml").write_text("- alpha\n- group\n- gamma\n")
    (root / "group" / "dckrsub.yml").write_text("- beta\n")
    return tmp_path, root, bin_dir


def run(tmp_path, root, bin_dir, *argv, **env):
    environ = {k: v for k, v in os.environ.items()
               if not k.startswith(("PORTMGR_", "FAKE_", "COMPOSE_"))}
    environ["PATH"] = f"{bin_dir}{os.pathsep}{environ.get('PATH', '')}"
    environ.update(env)
    # stdout is a pipe, as under cron: Python would block-buffer it by default.
    return subprocess.run(
        [sys.executable, "-m", "portmgr", *argv],
        cwd=str(root), env=environ,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def test_stack_header_comes_before_its_docker_output(tree):
    tmp_path, root, bin_dir = tree
    out = run(tmp_path, root, bin_dir, "b").stdout.splitlines()
    for stack, name in (("alpha", "alpha"), ("group/beta", "beta"), ("gamma", "gamma")):
        header = out.index(f"-> {stack}")
        first = next(i for i, line in enumerate(out) if line.startswith(f"docker-out {name} "))
        assert header < first, out
    # Without the env variables nothing else changes: no status suffix.
    assert not any(line.endswith(" OK") or " OK (" in line for line in out)


def test_log_dir_gets_each_stacks_output(tree):
    tmp_path, root, bin_dir = tree
    logs = tmp_path / "logs"
    result = run(tmp_path, root, bin_dir, "b", PORTMGR_LOG_DIR=str(logs), FAKE_FAIL="beta")
    out = result.stdout
    assert "docker-out" not in out and "docker-err" not in out
    assert "-> alpha OK (" in out
    assert "-> group/beta FAILED (" in out
    assert "-> gamma OK (" in out
    assert "Failed containers:\n- group/beta" in out

    assert sorted(os.listdir(logs)) == ["alpha.log", "gamma.log", "group__beta.log"]
    beta = (logs / "group__beta.log").read_text()
    assert beta.startswith("-> group/beta\n")
    assert "docker-out beta compose -f .portmgr-build.yml build --pull" in beta
    assert "docker-err beta" in beta
    assert "Error building group/beta!" in beta
    assert "alpha" not in beta


def test_log_dir_appends_a_second_command_in_the_same_run(tree):
    tmp_path, root, bin_dir = tree
    logs = tmp_path / "logs"
    run(tmp_path, root, bin_dir, "bp", PORTMGR_LOG_DIR=str(logs))
    alpha = (logs / "alpha.log").read_text()
    assert "build --pull" in alpha and " pull" in alpha.split("build --pull", 1)[1]
    assert alpha.count("-> alpha\n") == 2


def test_results_file_has_one_line_per_stack(tree):
    tmp_path, root, bin_dir = tree
    logs = tmp_path / "logs"
    results = tmp_path / "out" / "results.jsonl"
    run(tmp_path, root, bin_dir, "r", PORTMGR_LOG_DIR=str(logs), PORTMGR_RESULTS=str(results),
        FAKE_FAIL="gamma", TAG="v2")
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    assert [r["stack"] for r in rows] == ["alpha", "group/beta", "gamma"]
    assert [r["status"] for r in rows] == ["ok", "ok", "failed"]
    assert rows[0]["rc"] == 0 and rows[2]["rc"] != 0
    assert all(r["command"] == "r" for r in rows)
    assert rows[1]["log"] == str(logs / "group__beta.log")
    assert rows[1]["images"] == ["registry.example/beta:v2"]
    assert rows[0]["start"].endswith("+00:00")
    assert isinstance(rows[0]["duration_s"], float)
    assert set(rows[0]) == {"stack", "command", "rc", "status", "start", "duration_s", "log", "images"}


def test_results_without_log_dir_and_for_other_commands(tree):
    tmp_path, root, bin_dir = tree
    results = tmp_path / "results.jsonl"
    out = run(tmp_path, root, bin_dir, "p", PORTMGR_RESULTS=str(results)).stdout
    assert "-> alpha\n" in out
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    assert [r["log"] for r in rows] == [None, None, None]
    assert [r["images"] for r in rows] == [[], [], []]


def test_stop_file_skips_the_remaining_stacks(tree):
    tmp_path, root, bin_dir = tree
    logs = tmp_path / "logs"
    results = tmp_path / "results.jsonl"
    stop = tmp_path / "STOP"
    out = run(tmp_path, root, bin_dir, "b", PORTMGR_LOG_DIR=str(logs), PORTMGR_RESULTS=str(results),
              PORTMGR_STOP_FILE=str(stop), FAKE_TOUCH=str(stop), FAKE_TOUCH_IN="beta").stdout
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    # The stack that was running when the file appeared finishes; the rest is skipped.
    assert [r["status"] for r in rows] == ["ok", "ok", "skipped"]
    assert rows[2]["rc"] is None and rows[2]["log"] is None
    assert "-> gamma SKIPPED" in out
    assert "Skipped (stop file):\n- gamma" in out
    assert not (logs / "gamma.log").exists()


def test_stop_file_without_log_dir(tree):
    tmp_path, root, bin_dir = tree
    stop = tmp_path / "STOP"
    stop.write_text("")
    out = run(tmp_path, root, bin_dir, "b", PORTMGR_STOP_FILE=str(stop)).stdout
    assert "docker-out" not in out
    assert "-> alpha SKIPPED (stop file)" in out


@pytest.mark.parametrize("relative, name", [
    ("alpha", "alpha.log"),
    ("matrix-bridges/web", "matrix-bridges__web.log"),
    ("a/b/c", "a__b__c.log"),
])
def test_log_name(relative, name):
    assert runlog.log_name(relative) == name


@pytest.mark.parametrize("seconds, text", [
    (0, "0s"), (59.4, "59s"), (192, "3m12s"), (3600, "1h00m"), (4000, "1h06m"),
])
def test_format_duration(seconds, text):
    assert runlog.format_duration(seconds) == text


def test_service_images_expand_like_compose(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ARCH=arm64\nNAME='web'\n")
    monkeypatch.delenv("ARCH", raising=False)
    monkeypatch.delenv("NAME", raising=False)
    monkeypatch.delenv("UNSET", raising=False)
    monkeypatch.setenv("REG", "registry.example")
    services = {
        "a": {"image": "${REG}/${NAME}:${ARCH:-amd64}"},
        "b": {"image": "$REG/plain:${UNSET-dflt}"},
        "c": {"image": "x/${UNSET}"},
        "d": {"build": "."},
    }
    assert runlog.service_images(services, str(tmp_path)) == [
        "registry.example/web:arm64", "registry.example/plain:dflt", "x/${UNSET}",
    ]

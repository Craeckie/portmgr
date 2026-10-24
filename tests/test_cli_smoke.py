import subprocess
import sys


def test_no_args_prints_help_and_exits_1(tmp_path):
    # Run from an empty dir so traversal finds no compose targets.
    result = subprocess.run(
        [sys.executable, "-m", "portmgr"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    # argparse help lists the usage line and our registered command flags.
    assert "usage" in combined.lower()


def test_stray_word_is_an_error_and_runs_nothing(tmp_path):
    # A compose file makes the dir a target: nothing may run, docker or not.
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    for argv in (["l", "db"], ["pu", "l"], ["--force", "D"]):
        result = subprocess.run(
            [sys.executable, "-m", "portmgr", *argv],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, argv
        assert "unexpected argument" in result.stderr
        assert "combine commands as" in result.stderr
        assert "->" not in result.stdout


def test_help_exits_0(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "portmgr", "-h"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Encrypt/seal" in result.stdout

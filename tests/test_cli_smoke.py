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

import os
import subprocess
import sys

import pytest

pytest.importorskip("pyrage")


def run_portmgr(args, cwd, passphrase="correct horse battery staple"):
    # Inherit PATH/PYTHONPATH etc. so the installed package is importable.
    full_env = dict(os.environ)
    full_env["PORTMGR_PASSPHRASE"] = passphrase
    return subprocess.run(
        [sys.executable, "-m", "portmgr", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_seal_unseal_round_trip_without_compose_file(tmp_path):
    # No docker-compose.yml and no dckrsub.yml: traversal finds no stacks, so
    # this only works because E/D are registered as 'standalone' and fall back
    # to the base directory.
    assert not (tmp_path / "docker-compose.yml").exists()
    secret = tmp_path / "app.env"
    original = "DB_PASSWORD=hunter2\n"
    secret.write_text(original)

    sealed = run_portmgr(["E", "app.env"], cwd=tmp_path)
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    assert (tmp_path / "app.env.age").is_file()

    secret.unlink()  # drop plaintext so unseal has to recreate it

    unsealed = run_portmgr(["D"], cwd=tmp_path)
    assert unsealed.returncode == 0, unsealed.stdout + unsealed.stderr
    assert secret.read_text() == original


def test_non_standalone_command_skips_compose_less_dir(tmp_path):
    # 'S' (status) is not standalone; in a dir with no stacks it must produce no
    # per-directory output, confirming the fallback is opt-in.
    result = run_portmgr(["S"], cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "->" not in result.stdout

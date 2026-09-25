"""CHANGELOG.md is the release message: CI publishes the section of the version
being released as the GitHub release body (.github/scripts/release-check.sh)."""

import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".github" / "scripts"

CHANGELOG = """\
# Changelog

## [Unreleased]

## [1.10.0] - 2026-01-03

### Added
- Ten

## [1.2.0] - 2026-01-02

### Added
- New thing

## [1.1.0] - 2026-01-01

### Fixed
- Old thing

## [1.0.0] - 2025-12-31

"""


def section(version, changelog):
    return subprocess.run(
        ["bash", str(SCRIPTS / "changelog-section.sh"), version, str(changelog)],
        capture_output=True,
        text=True,
    )


def test_current_version_has_changelog_section():
    # A version bump without its CHANGELOG.md section must fail before anything is published.
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    result = section(version, ROOT / "CHANGELOG.md")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_section_is_only_that_version(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG)
    assert section("1.2.0", changelog).stdout == "### Added\n- New thing\n"
    assert section("1.1.0", changelog).stdout == "### Fixed\n- Old thing\n"


def test_missing_section_fails(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG)
    result = section("1.3.0", changelog)
    assert result.returncode != 0
    assert "1.3.0" in result.stderr


def test_version_prefix_does_not_match(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG)
    assert section("1.2", changelog).returncode != 0


def test_empty_section_fails(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG)
    assert section("1.0.0", changelog).returncode != 0


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, check=True, capture_output=True,
    )


def make_repo(tmp_path, version, tags=(), changelog=CHANGELOG):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n')
    (repo / "CHANGELOG.md").write_text(changelog)
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    for tag in tags:
        git(repo, "tag", tag)
    return repo


def release_check(repo):
    output = repo / "gh-output"
    result = subprocess.run(
        ["bash", str(SCRIPTS / "release-check.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_OUTPUT": str(output), "GITHUB_REPOSITORY": "o/r"},
    )
    outputs = dict(
        line.split("=", 1) for line in output.read_text().splitlines()
    ) if output.exists() else {}
    return result, outputs


def test_existing_tag_is_a_noop(tmp_path):
    repo = make_repo(tmp_path, "1.2.0", tags=["v1.1.0", "v1.2.0"])
    result, outputs = release_check(repo)
    assert result.returncode == 0, result.stderr
    assert outputs == {"tag": "v1.2.0", "should_release": "false"}
    assert not (repo / "notes.md").exists()


def test_bump_releases_with_changelog_notes(tmp_path):
    # Legacy tags without the v prefix (1.4.8) are not versions to compare against.
    repo = make_repo(tmp_path, "1.2.0", tags=["v1.0.0", "v1.1.0", "1.4.8"])
    result, outputs = release_check(repo)
    assert result.returncode == 0, result.stderr
    assert outputs == {"tag": "v1.2.0", "should_release": "true"}
    assert (repo / "notes.md").read_text() == (
        "### Added\n- New thing\n\n"
        "**Full Changelog**: https://github.com/o/r/compare/v1.1.0...v1.2.0\n"
    )


def test_versions_compare_numerically(tmp_path):
    repo = make_repo(tmp_path, "1.10.0", tags=["v1.2.0"])
    result, outputs = release_check(repo)
    assert result.returncode == 0, result.stderr
    assert outputs["should_release"] == "true"


def test_first_release_has_no_compare_link(tmp_path):
    repo = make_repo(tmp_path, "1.2.0")
    result, outputs = release_check(repo)
    assert result.returncode == 0, result.stderr
    assert (repo / "notes.md").read_text() == "### Added\n- New thing\n"


def test_version_below_latest_tag_fails(tmp_path):
    repo = make_repo(tmp_path, "1.1.0", tags=["v1.2.0"])
    result, outputs = release_check(repo)
    assert result.returncode != 0
    assert "v1.2.0" in result.stderr
    assert "should_release" not in outputs


def test_bump_without_changelog_section_fails(tmp_path):
    repo = make_repo(tmp_path, "1.3.0", tags=["v1.2.0"])
    result, outputs = release_check(repo)
    assert result.returncode != 0
    assert "CHANGELOG.md" in result.stderr
    assert "should_release" not in outputs

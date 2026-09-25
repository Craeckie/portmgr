#!/usr/bin/env bash
# Decide whether the checked-out commit releases a new version (release.yml).
# Outputs tag=v<version> and should_release=true|false to $GITHUB_OUTPUT; on a
# release, writes the version's CHANGELOG.md section to notes.md as the release body.
set -euo pipefail

version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n1)
tag="v$version"

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  echo "$tag already exists, nothing to release"
  printf 'tag=%s\nshould_release=false\n' "$tag" >>"$GITHUB_OUTPUT"
  exit 0
fi

# Legacy tags without the v prefix (1.4.7, 1.4.8) are not compared against.
latest=$(git tag -l 'v*' | sort -V | tail -n1)
if [ -n "$latest" ] && [ "$(printf '%s\n%s\n' "$latest" "$tag" | sort -V | tail -n1)" != "$tag" ]; then
  echo "$tag is not newer than the latest release $latest" >&2
  exit 1
fi

notes=$("$(dirname "$0")/changelog-section.sh" "$version" CHANGELOG.md)
if [ -n "$latest" ]; then
  notes+=$'\n\n'"**Full Changelog**: ${GITHUB_SERVER_URL:-https://github.com}/$GITHUB_REPOSITORY/compare/$latest...$tag"
fi
printf '%s\n' "$notes" >notes.md

echo "Releasing $tag (previous: ${latest:-none})"
printf 'tag=%s\nshould_release=true\n' "$tag" >>"$GITHUB_OUTPUT"

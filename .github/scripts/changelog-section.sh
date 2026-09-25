#!/usr/bin/env bash
# Print the body of CHANGELOG.md's "## [<version>]" section, without its heading
# and surrounding blank lines. Fails if the section is missing or empty.
# Usage: changelog-section.sh <version> [CHANGELOG.md]
set -euo pipefail

version=$1
changelog=${2:-CHANGELOG.md}

body=$(awk -v heading="## [$version]" '
  /^## / { if (found) exit; if (index($0, heading) == 1) { found = 1; next } }
  found { print }
' "$changelog" | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}')

if [ -z "${body//[[:space:]]/}" ]; then
  echo "$changelog has no entry for $version: add a '## [$version] - <date>' section" >&2
  exit 1
fi
printf '%s\n' "$body"

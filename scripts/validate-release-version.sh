#!/usr/bin/env bash

set -euo pipefail

lane="${1:-}"
tag="${2:-}"
expected_version="${3:-}"

numeric_identifier='(0|[1-9][0-9]*)'
prerelease_identifier='([0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*|0|[1-9][0-9]*)'
# MUTX release tags deliberately reject SemVer build metadata. GitHub desktop
# discovery and the production promotion lane do not publish or resolve it.
semver_pattern="${numeric_identifier}\\.${numeric_identifier}\\.${numeric_identifier}(-${prerelease_identifier}(\\.${prerelease_identifier})*)?"

case "${lane}" in
  desktop)
    prefix="v"
    ;;
  cli)
    prefix="cli-v"
    ;;
  sdk)
    prefix="sdk-v"
    ;;
  *)
    echo "Unsupported release lane: ${lane:-<empty>}" >&2
    exit 2
    ;;
esac

if [[ "${tag}" != "${prefix}"* ]]; then
  echo "Release tag ${tag:-<empty>} does not belong to the ${lane} lane." >&2
  exit 1
fi

version="${tag#"${prefix}"}"
if [[ ! "${version}" =~ ^${semver_pattern}$ ]]; then
  echo "Unsupported ${lane} release tag: ${tag:-<empty>}. Build metadata is not published." >&2
  exit 1
fi

if [[ -n "${expected_version}" && "${version}" != "${expected_version}" ]]; then
  echo "Release tag ${tag} does not match expected version ${expected_version}." >&2
  exit 1
fi

printf '%s\n' "${version}"

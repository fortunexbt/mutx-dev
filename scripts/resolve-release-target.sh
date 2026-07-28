#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
event_name="${GITHUB_EVENT_NAME:-}"
ref_name="${GITHUB_REF_NAME:-}"
ref="${GITHUB_REF:-}"
event_sha="${GITHUB_SHA:-}"
requested_version="${REQUESTED_VERSION:-}"

case "${event_name}" in
  workflow_dispatch)
    if [[ -z "${requested_version}" ]]; then
      echo "Manual releases require an exact desktop tag such as v1.2.3." >&2
      exit 1
    fi
    target_tag="${requested_version}"
    release_lane="desktop"
    ;;
  push)
    case "${ref_name}" in
      cli-v*)
        target_tag="${ref_name}"
        release_lane="cli"
        ;;
      sdk-v*)
        target_tag="${ref_name}"
        release_lane="sdk"
        ;;
      v*)
        target_tag="${ref_name}"
        release_lane="desktop"
        ;;
      *)
        echo "Unsupported release tag: ${ref_name}" >&2
        exit 1
        ;;
    esac

    ;;
  *)
    echo "Unsupported release event: ${event_name:-<empty>}" >&2
    exit 1
    ;;
esac

version="$(bash "${ROOT_DIR}/scripts/validate-release-version.sh" "${release_lane}" "${target_tag}")"

tag_ref="refs/tags/${target_tag}"
if ! git show-ref --verify --quiet "${tag_ref}"; then
  echo "Release tag does not exist: ${target_tag}" >&2
  exit 1
fi

tag_object_type="$(git cat-file -t "${tag_ref}")"
if [[ "${tag_object_type}" != "tag" ]]; then
  echo "Release tag must be an annotated tag object: ${target_tag}" >&2
  exit 1
fi

target_commit="$(git rev-parse --verify "${tag_ref}^{commit}")"

if ! git show-ref --verify --quiet refs/remotes/origin/main; then
  echo "Release trust requires the fetched refs/remotes/origin/main reference." >&2
  exit 1
fi
if ! git merge-base --is-ancestor "${target_commit}" refs/remotes/origin/main; then
  echo "Release target ${target_commit} is not an ancestor of origin/main." >&2
  exit 1
fi

if [[ "${event_name}" == "push" ]]; then
  if [[ "${ref}" != "${tag_ref}" ]]; then
    echo "Release event ref ${ref:-<empty>} does not match ${tag_ref}." >&2
    exit 1
  fi
  if [[ ! "${event_sha}" =~ ^[0-9a-f]{40}$ || "${event_sha}" != "${target_commit}" ]]; then
    echo "Release event SHA must exactly match the peeled ${target_tag} commit." >&2
    exit 1
  fi
fi

case "${release_lane}" in
  desktop)
    source_version="$(
      git show "${target_commit}:package.json" |
        node -e '
          let body = ""
          process.stdin.setEncoding("utf8")
          process.stdin.on("data", (chunk) => { body += chunk })
          process.stdin.on("end", () => {
            const value = JSON.parse(body).version
            if (typeof value !== "string" || value.length === 0) process.exit(1)
            process.stdout.write(value)
          })
        '
    )"
    ;;
  cli)
    source_version="$(
      git show "${target_commit}:pyproject.toml" |
        python3 -c 'import sys, tomllib; print(tomllib.loads(sys.stdin.read())["project"]["version"])'
    )"
    ;;
  sdk)
    source_version="$(
      git show "${target_commit}:sdk/pyproject.toml" |
        python3 -c 'import sys, tomllib; print(tomllib.loads(sys.stdin.read())["project"]["version"])'
    )"
    ;;
esac

version="$(
  bash "${ROOT_DIR}/scripts/validate-release-version.sh" \
    "${release_lane}" "${target_tag}" "${source_version}"
)"
promote_production=false
if [[ "${release_lane}" == "desktop" && "${version}" != *-* ]]; then
  promote_production=true
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "target_tag=${target_tag}"
    echo "target_commit=${target_commit}"
    echo "target_version=${version}"
    echo "release_lane=${release_lane}"
    echo "promote_production=${promote_production}"
  } >> "${GITHUB_OUTPUT}"
fi

echo "Resolved ${target_tag} to ${target_commit} for the ${release_lane} release lane."

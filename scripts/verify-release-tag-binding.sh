#!/usr/bin/env bash

set -euo pipefail

release_tag="${RELEASE_TAG:-}"
release_sha="${RELEASE_SHA:-}"

if [[ -z "${release_tag}" ]]; then
  echo "RELEASE_TAG is required for release tag verification." >&2
  exit 1
fi
if [[ ! "${release_sha}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "RELEASE_SHA must be a full lowercase 40-character Git commit SHA." >&2
  exit 1
fi
if ! git show-ref --verify --quiet "refs/tags/${release_tag}"; then
  echo "Release tag does not exist in the checkout: ${release_tag}" >&2
  exit 1
fi
if [[ "$(git cat-file -t "refs/tags/${release_tag}")" != "tag" ]]; then
  echo "Release tag must remain an annotated tag object: ${release_tag}" >&2
  exit 1
fi

local_tag_object_sha="$(git rev-parse "refs/tags/${release_tag}")"
local_target_sha="$(git rev-parse "refs/tags/${release_tag}^{commit}")"
if [[ "${local_target_sha}" != "${release_sha}" ]]; then
  echo "${release_tag} no longer targets the originally resolved commit ${release_sha}." >&2
  exit 1
fi

if ! immutable_releases_enabled="$(
  gh api \
    -H 'X-GitHub-Api-Version: 2026-03-10' \
    "repos/${GITHUB_REPOSITORY}/immutable-releases" \
    --jq '.enabled'
)"; then
  echo "Repository immutable releases must be enabled before release publication." >&2
  exit 1
fi
if [[ "${immutable_releases_enabled}" != "true" ]]; then
  echo "Repository immutable releases must be enabled before release publication." >&2
  exit 1
fi

ref_state="$(
  gh api "repos/${GITHUB_REPOSITORY}/git/ref/tags/${release_tag}" \
    --jq '[.ref, .object.type, .object.sha] | @tsv'
)"
expected_ref_state="$(printf 'refs/tags/%s\ttag\t%s' "${release_tag}" "${local_tag_object_sha}")"
if [[ "${ref_state}" != "${expected_ref_state}" ]]; then
  echo "GitHub tag reference is not the exact annotated tag ${release_tag}." >&2
  exit 1
fi

tag_state="$(
  gh api "repos/${GITHUB_REPOSITORY}/git/tags/${local_tag_object_sha}" \
    --jq '[.object.type, .object.sha, .verification.verified, .verification.reason] | @tsv'
)"
expected_tag_state="$(printf 'commit\t%s\ttrue\tvalid' "${release_sha}")"
if [[ "${tag_state}" != "${expected_tag_state}" ]]; then
  echo "${release_tag} must be cryptographically signed, GitHub-verified, and target ${release_sha}." >&2
  exit 1
fi

printf 'Verified immutable signed tag binding: %s -> %s\n' "${release_tag}" "${release_sha}"

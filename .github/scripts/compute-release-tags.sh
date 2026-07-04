#!/bin/sh
# Emit release tags for the telemetry server workflows.
#
# Usage:
#   .github/scripts/compute-release-tags.sh base
#   .github/scripts/compute-release-tags.sh suffix amd64
#
# Output is one tag per line.
set -eu

mode="${1:-base}"
arch="${2:-}"

case "${GITHUB_REF_TYPE:-}" in
  branch)
    tags="${GITHUB_REF_NAME:-}"
    if [ "${GITHUB_REF_NAME:-}" = "main" ]; then
      tags="${tags} latest"
    fi
    ;;
  tag)
    version="${GITHUB_REF_NAME#v}"
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f1,2)
    tags="$version $minor $major latest"
    ;;
  *)
    tags=""
    ;;
esac

for tag in $tags; do
  case "$mode" in
    base)
      printf '%s\n' "$tag"
      ;;
    suffix)
      if [ -z "$arch" ]; then
        echo "arch argument is required for suffix mode" >&2
        exit 1
      fi
      printf '%s-%s\n' "$tag" "$arch"
      ;;
    *)
      echo "unknown mode: $mode" >&2
      exit 1
      ;;
  esac
done

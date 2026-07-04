#!/usr/bin/env bash
# GHCR cleanup script
# Expects: GH_TOKEN env var (GitHub PAT with delete:packages), and GITHUB_REPOSITORY

set -u

if [ -z "${GH_TOKEN:-}" ]; then
    echo "==> GHCR_DELETE_TOKEN is not set; skipping GHCR cleanup"
    exit 0
fi

# Derive owner/repo
OWNER_LC=${OWNER_LC:-}
if [ -z "$OWNER_LC" ]; then
    # fallback to GITHUB_REPOSITORY owner
    if [ -n "${GITHUB_REPOSITORY:-}" ]; then
        OWNER_LC=${GITHUB_REPOSITORY%%/*}
    else
        echo "==> Cannot determine repository owner; ensure OWNER_LC or GITHUB_REPOSITORY is set"
        exit 0
    fi
fi

REPO_NAME="${GITHUB_REPOSITORY#*/}"
PACKAGE_NAME="${REPO_NAME,,}"

page=1
per_page=100
max_pages=${MAX_PAGES:-200}

while :; do
    if [ "$page" -gt "$max_pages" ]; then
        echo "==> Reached max page ${max_pages}; aborting GHCR cleanup"
        break
    fi

    tmpfile=$(mktemp)
    http_status=$(curl -sS -o "$tmpfile" -w '%{http_code}' \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/orgs/${OWNER_LC}/packages/container/${PACKAGE_NAME}/versions?per_page=${per_page}&page=${page}") || {
        echo "==> curl failed; aborting GHCR cleanup"
        rm -f "$tmpfile"
        break
    }
    resp=$(cat "$tmpfile")
    rm -f "$tmpfile"

    echo "==> GHCR API HTTP status: ${http_status}"
    if ! printf '%s' "$http_status" | grep -E '^[0-9]+$' >/dev/null 2>&1; then
        echo "==> Invalid HTTP status value; aborting GHCR cleanup"
        break
    fi
    if [ "$http_status" -ne 200 ]; then
        echo "==> Non-200 HTTP status; aborting GHCR cleanup"
        break
    fi

    if [ -z "$resp" ] || [ "$resp" = "[]" ]; then
        echo "==> No package versions returned; nothing to do"
        break
    fi

    # Ensure response is a JSON array
    if ! echo "$resp" | jq -e 'if type=="array" then . else empty end' >/dev/null 2>&1; then
        echo "==> Unexpected API response; aborting GHCR cleanup"
        break
    fi

    items=$(echo "$resp" | jq 'length')
    mapfile -t entries < <(echo "$resp" | jq -r '.[] | "\(.id)\t\(.metadata.container.tags | join(","))"')
    found_deleted_in_page=0

    for entry in "${entries[@]}"; do
        IFS=$'\t' read -r id tags_str <<<"$entry"
        # Only delete UNTAGGED orphan versions.
        # Multi-arch manifests reference per-arch images by digest, so deleting
        # tagged versions (even -amd64/-arm64 suffixed ones) breaks pulls.
        if [ -z "$tags_str" ]; then
            echo "==> Deleting untagged GHCR package version ${id}"
            curl -fsS -X DELETE \
                -H "Authorization: Bearer ${GH_TOKEN}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/orgs/${OWNER_LC}/packages/container/${PACKAGE_NAME}/versions/${id}" ||
                echo "  (failed to delete version ${id}, continuing)"
            found_deleted_in_page=$((found_deleted_in_page + 1))
        else
            echo "==> Keeping GHCR package version ${id} (tags: ${tags_str})"
        fi
    done

    # Stop early if no deletions on last page
    if [ "$found_deleted_in_page" -eq 0 ] && [ "$items" -lt "$per_page" ]; then
        echo "==> No deletable versions remain; stopping cleanup"
        break
    fi

    page=$((page + 1))
done

exit 0

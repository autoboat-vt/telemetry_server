# Custom tailscale image with OAuth credentials baked in.
#
# WHY: the upstream `tailscale/tailscale:latest` image reads TS_CLIENT_ID and
# TS_CLIENT_SECRET from environment variables at runtime. That requires the
# host to provide them via .env, which means a manual paste on every new host.
#
# This image bakes the credentials in as ENV at build time, so the image is
# self-contained: `docker compose --profile tailscale up -d` works with zero
# host-side configuration. The build happens in GitHub Actions, where the
# secrets ARE available (as org secrets/vars), so they never touch a developer
# machine or the repo's git history.
#
# SECURITY: this image MUST be private on GHCR. The baked-in OAuth client
# secret grants tailnet access (register devices as tag:server, SSH to
# tag:server hosts, and -- because we use one client with both scopes --
# read/write the tailnet policy). Anyone who can `docker pull` this image can
# extract the secret. Make the GHCR package private at:
#   https://github.com/orgs/autoboat-vt/packages/container/telemetry_server-tailscale/settings
# And require `docker login ghcr.io` on the host before `docker compose pull`.
#
# Uses the SAME OAuth client as the GitOps ACL workflow (one client with both
# `devices:core` and `policy_file` scopes). Build args are passed from the
# build workflow:
#   TS_CLIENT_ID      - non-secret, starts with k. Read from org variable
#                       TS_OAUTH_ID (renamed here to match containerboot's
#                       expected env var name).
#   TS_CLIENT_SECRET  - secret, starts with tskey-client-. Read from org
#                       secret TS_OAUTH_SECRET.
#
# AUTH METHOD: we bake the OAuth secret into TS_AUTHKEY (not TS_CLIENT_SECRET)
# because of a containerboot v1.98 bug: when TS_CLIENT_ID/TS_CLIENT_SECRET are
# used, containerboot calls `tailscale up` which internally invokes
# `check-prefs` BEFORE the OAuth client auth completes. tailscaled sees an
# unauthenticated actor and rejects with HTTP 403
# ("calling actor does not have enough permissions to perform this function").
#
# Using TS_AUTHKEY with the OAuth secret avoids this: per Tailscale docs,
# `TS_AUTHKEY` accepts an OAuth client secret directly, and auth + pref
# validation happen together in a single `tailscale up --auth-key=<secret>`
# call. The tag must be passed via TS_EXTRA_ARGS=--advertise-tags=tag:server
# (already set in docker-compose.yml).

FROM tailscale/tailscale:latest

ARG TS_CLIENT_ID
ARG TS_CLIENT_SECRET

# Persist as runtime env vars. containerboot reads these on startup.
# These are baked into the image layers -- hence the "image MUST be private"
# warning above.
#
# We set TS_AUTHKEY to the OAuth secret (not TS_CLIENT_SECRET) -- see the
# AUTH METHOD note above. TS_CLIENT_ID is kept for debugging/identification
# but is not used by containerboot when TS_AUTHKEY is set.
ENV TS_CLIENT_ID=${TS_CLIENT_ID}
ENV TS_AUTHKEY=${TS_CLIENT_SECRET}

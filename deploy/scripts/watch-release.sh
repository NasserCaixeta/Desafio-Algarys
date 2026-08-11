#!/usr/bin/env bash

set -Eeuo pipefail

readonly deploy_path=/opt/clinic-confirmations
readonly repository_url=https://github.com/NasserCaixeta/Desafio-Algarys.git
readonly deploy_command=/usr/local/sbin/clinic-confirmations-deploy
readonly env_file="$deploy_path/.env.production"

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

read_env_value() {
  local key=$1
  awk -F= -v key="$key" '$1 == key { print substr($0, index($0, "=") + 1); exit }' "$env_file"
}

if [[ $EUID -ne 0 ]]; then
  echo "release watcher must run as root" >&2
  exit 77
fi

[[ -d $deploy_path/.git ]] || {
  echo "deploy checkout not found: $deploy_path" >&2
  exit 66
}
[[ -f $env_file ]] || {
  echo "production environment not found: $env_file" >&2
  exit 66
}

target_commit=$(git ls-remote "$repository_url" refs/heads/main | awk 'NR == 1 { print $1 }')
if [[ ! $target_commit =~ ^[0-9a-f]{40}$ ]]; then
  echo "could not resolve origin/main" >&2
  exit 69
fi

target_tag="sha-$target_commit"
current_commit=$(git -C "$deploy_path" rev-parse HEAD)
current_tag=$(read_env_value IMAGE_TAG)

if [[ $current_commit == "$target_commit" && $current_tag == "$target_tag" ]]; then
  log "release is already current: $target_tag"
  exit 0
fi

owner=$(read_env_value GHCR_OWNER | tr '[:upper:]' '[:lower:]')
if [[ ! $owner =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  echo "invalid GHCR_OWNER in .env.production" >&2
  exit 65
fi

for image in clinic-confirmations-api clinic-confirmations-worker clinic-confirmations-frontend; do
  reference="ghcr.io/$owner/$image:$target_tag"
  if ! timeout 30 docker manifest inspect "$reference" >/dev/null 2>&1; then
    log "release is not published yet: $reference"
    exit 0
  fi
done

log "published release found: $target_tag"
exec "$deploy_command" "$target_commit" "$target_tag"

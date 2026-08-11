#!/usr/bin/env bash

set -Eeuo pipefail

readonly exit_usage=64
root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
readonly root_dir
readonly env_file="$root_dir/.env.production"
readonly state_dir="$root_dir/.deploy"
readonly backup_dir="$state_dir/backups"
readonly lock_file="/tmp/clinic-confirmations-deploy.lock"

target_tag=${1:-}
previous_commit=${2:-}
release_switched=false
previous_tag=""

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
  log "ERROR: $*" >&2
  return 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

read_env_value() {
  local key=$1
  awk -F= -v key="$key" '$1 == key { print substr($0, index($0, "=") + 1); exit }' "$env_file"
}

write_release() {
  local image_tag=$1
  local temporary
  temporary=$(mktemp "$root_dir/.env.production.XXXXXX")

  awk -v image_tag="$image_tag" '
    BEGIN { image_found = 0; version_found = 0 }
    /^IMAGE_TAG=/ { print "IMAGE_TAG=" image_tag; image_found = 1; next }
    /^APP_VERSION=/ { print "APP_VERSION=" image_tag; version_found = 1; next }
    { print }
    END {
      if (!image_found) print "IMAGE_TAG=" image_tag
      if (!version_found) print "APP_VERSION=" image_tag
    }
  ' "$env_file" > "$temporary"

  chmod 600 "$temporary"
  mv "$temporary" "$env_file"
}

compose() {
  docker compose "${compose_args[@]}" "$@"
}

container_state() {
  local service=$1
  local container_id
  container_id=$(compose ps -q "$service")
  if [[ -z $container_id ]]; then
    printf 'missing'
    return
  fi

  docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id"
}

wait_for_services() {
  local timeout_seconds=$1
  shift
  local services=("$@")
  local deadline=$((SECONDS + timeout_seconds))
  local all_healthy service state

  while ((SECONDS < deadline)); do
    all_healthy=true
    for service in "${services[@]}"; do
      state=$(container_state "$service")
      if [[ $state != "running:healthy" ]]; then
        all_healthy=false
        break
      fi
    done

    if [[ $all_healthy == true ]]; then
      return 0
    fi
    sleep 5
  done

  for service in "${services[@]}"; do
    log "$service: $(container_state "$service")"
  done
  return 1
}

verify_application() {
  compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).read()"
  compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/status', timeout=5).read()"

  local domain
  domain=$(read_env_value DOMAIN)
  [[ -n $domain ]] || fail "DOMAIN is missing from .env.production"
  curl --fail --silent --show-error --max-time 10 "https://$domain/health/live" >/dev/null
}

start_application() {
  compose up -d postgres redis
  wait_for_services 120 postgres redis

  compose up --no-deps --force-recreate --abort-on-container-exit --exit-code-from migrate migrate
  compose up -d --no-deps api worker scheduler frontend
  wait_for_services 180 postgres redis api worker scheduler frontend

  compose up -d --no-deps nginx
  wait_for_services 120 postgres redis api worker scheduler frontend nginx
  verify_application
}

create_backup() {
  local postgres_id backup_path temporary
  postgres_id=$(compose ps -q postgres)
  [[ -n $postgres_id ]] || return 0
  [[ $(docker inspect --format '{{.State.Status}}' "$postgres_id") == running ]] || return 0

  mkdir -p "$backup_dir"
  backup_path="$backup_dir/$(date -u +'%Y%m%dT%H%M%SZ')-$previous_tag.dump"
  temporary="$backup_path.tmp"
  log "creating PostgreSQL backup"
  # The variables are expanded by the shell inside the PostgreSQL container.
  # shellcheck disable=SC2016
  compose exec -T postgres sh -eu -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary"
  mv "$temporary" "$backup_path"

  mapfile -t old_backups < <(find "$backup_dir" -maxdepth 1 -type f -name '*.dump' -printf '%T@ %p\n' \
    | sort -rn | tail -n +6 | cut -d' ' -f2-)
  if ((${#old_backups[@]} > 0)); then
    rm -- "${old_backups[@]}"
  fi
}

rollback() {
  local original_status=${1:-1}
  local rollback_failed=0
  trap - ERR INT TERM
  set +e

  log "deployment failed; starting image rollback"
  if [[ -n $previous_commit && $previous_commit =~ ^[0-9a-f]{40}$ ]]; then
    git -C "$root_dir" checkout --detach "$previous_commit" || rollback_failed=1
  fi

  if [[ $release_switched == true && -n $previous_tag ]]; then
    write_release "$previous_tag" || rollback_failed=1
    compose pull migrate api worker scheduler frontend nginx || rollback_failed=1
    compose up -d postgres redis || rollback_failed=1
    compose up -d --no-deps api worker scheduler frontend || rollback_failed=1
    wait_for_services 180 postgres redis api worker scheduler frontend || rollback_failed=1
    compose up -d --no-deps nginx || rollback_failed=1
    wait_for_services 120 postgres redis api worker scheduler frontend nginx || rollback_failed=1
    verify_application || rollback_failed=1
    if [[ $rollback_failed -eq 0 ]]; then
      log "rollback completed with image tag $previous_tag"
    else
      log "ERROR: rollback did not return every service to a healthy state" >&2
    fi
  else
    log "release was not switched; only the server checkout was restored"
  fi

  exit "$original_status"
}

if [[ ! $target_tag =~ ^sha-[0-9a-f]{40}$ ]]; then
  echo "usage: deploy.sh sha-<40-character-commit> [previous-commit]" >&2
  exit "$exit_usage"
fi

if [[ -n $previous_commit && ! $previous_commit =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid previous commit SHA" >&2
  exit "$exit_usage"
fi

current_commit=$(git -C "$root_dir" rev-parse HEAD)
if [[ $target_tag != "sha-$current_commit" ]]; then
  echo "image tag does not match the checked-out commit" >&2
  exit "$exit_usage"
fi

trap 'rollback $?' ERR
trap 'rollback 130' INT
trap 'rollback 143' TERM

[[ -f $env_file ]] || fail "missing $env_file"
require_command curl
require_command docker
require_command flock
require_command git

mkdir -p "$state_dir" "$backup_dir"
if [[ ${DEPLOY_LOCK_HELD:-0} != 1 ]]; then
  exec 9>"$lock_file"
  flock -n 9 || fail "another deployment is already running"
fi

compose_args=(
  --project-directory "$root_dir"
  --env-file "$env_file"
  -f "$root_dir/compose.yaml"
  -f "$root_dir/compose.prod.yaml"
)
if [[ -f $root_dir/compose.vps.yaml ]]; then
  compose_args+=(-f "$root_dir/compose.vps.yaml")
fi

previous_tag=$(read_env_value IMAGE_TAG)
[[ -n $previous_tag ]] || fail "IMAGE_TAG is missing from .env.production"

if [[ $previous_tag == "$target_tag" ]]; then
  log "release $target_tag is already configured; verifying health"
  wait_for_services 120 postgres redis api worker scheduler frontend nginx
  verify_application
  printf '%s\n' "$target_tag" > "$state_dir/current-tag"
  git -C "$root_dir" rev-parse HEAD > "$state_dir/current-commit"
  trap - ERR INT TERM
  exit 0
fi

log "validating release $target_tag"
IMAGE_TAG="$target_tag" APP_VERSION="$target_tag" compose config --quiet
IMAGE_TAG="$target_tag" APP_VERSION="$target_tag" compose pull migrate api worker scheduler frontend nginx

create_backup
write_release "$target_tag"
release_switched=true

log "applying migrations and replacing application containers"
start_application

printf '%s\n' "$previous_tag" > "$state_dir/previous-tag"
printf '%s\n' "$target_tag" > "$state_dir/current-tag"
if [[ -n $previous_commit ]]; then
  printf '%s\n' "$previous_commit" > "$state_dir/previous-commit"
fi
git -C "$root_dir" rev-parse HEAD > "$state_dir/current-commit"

trap - ERR INT TERM
log "deployment completed successfully: $target_tag"
compose ps -a

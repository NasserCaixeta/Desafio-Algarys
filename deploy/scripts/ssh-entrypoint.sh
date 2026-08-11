#!/usr/bin/env bash

set -Eeuo pipefail
set -f

readonly deploy_command=/usr/local/sbin/clinic-confirmations-deploy
original_command=${SSH_ORIGINAL_COMMAND:-}

read -r action commit_sha image_tag unexpected <<< "$original_command"

if [[ $action != deploy || -n ${unexpected:-} ]]; then
  echo "only the production deploy command is allowed" >&2
  exit 77
fi

if [[ ! ${commit_sha:-} =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid commit SHA" >&2
  exit 64
fi

if [[ ${image_tag:-} != "sha-$commit_sha" ]]; then
  echo "image tag does not match the commit SHA" >&2
  exit 64
fi

exec sudo -n "$deploy_command" "$commit_sha" "$image_tag"

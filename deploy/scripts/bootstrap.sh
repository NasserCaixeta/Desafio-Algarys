#!/usr/bin/env bash

set -Eeuo pipefail

readonly deploy_path=/opt/clinic-confirmations

if [[ $EUID -ne 0 ]]; then
  echo "bootstrap must run as root" >&2
  exit 77
fi

if [[ $# -ne 2 ]]; then
  echo "usage: bootstrap.sh <commit-sha> <image-tag>" >&2
  exit 64
fi

commit_sha=$1
image_tag=$2

if [[ ! $commit_sha =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid commit SHA" >&2
  exit 64
fi

if [[ $image_tag != "sha-$commit_sha" ]]; then
  echo "image tag does not match the commit SHA" >&2
  exit 64
fi

if [[ ! -d $deploy_path/.git ]]; then
  echo "deploy path is not a Git checkout: $deploy_path" >&2
  exit 66
fi

cd "$deploy_path"

command -v flock >/dev/null 2>&1 || {
  echo "required command not found: flock" >&2
  exit 69
}
exec 9>/tmp/clinic-confirmations-deploy.lock
flock -n 9 || {
  echo "another deployment is already running" >&2
  exit 75
}

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "tracked changes found on the server; refusing to overwrite them" >&2
  exit 65
fi

previous_commit=$(git rev-parse HEAD)
git fetch --prune origin main

if ! git cat-file -e "$commit_sha^{commit}"; then
  echo "commit is not available after fetching origin/main" >&2
  exit 65
fi

if ! git merge-base --is-ancestor "$commit_sha" origin/main; then
  echo "commit is not part of origin/main" >&2
  exit 65
fi

if [[ $commit_sha != "$previous_commit" ]] && git merge-base --is-ancestor "$commit_sha" "$previous_commit"; then
  echo "refusing to deploy a commit older than the current checkout" >&2
  exit 65
fi

git checkout --detach "$commit_sha"
export DEPLOY_LOCK_HELD=1
exec ./deploy/scripts/deploy.sh "$image_tag" "$previous_commit"

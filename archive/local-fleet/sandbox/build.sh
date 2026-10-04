#!/usr/bin/env bash
# build.sh — install Apple `container`, boot it, and build the botfiles-agent
# sandbox image. Idempotent: re-run any time (e.g. after editing AGENTS.md).
# See .botfile/memory/tools/sandbox.md.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root == build context

command -v container >/dev/null || brew install container
container system status >/dev/null 2>&1 || container system start --enable-kernel-install

container build -t botfiles-agent -f sandbox/Containerfile .
echo "built image:"
container image list | grep -E 'NAME|botfiles-agent' || true

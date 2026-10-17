#!/usr/bin/env bash
# Clone the repo into a temp folder, install exactly like the README and CI, then run every check.
# Usage: scripts/clean_clone_check.sh [git-url-or-path] [branch]   (defaults: this repo's origin, current branch)
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
src="${1:-$(git -C "$here" remote get-url origin)}"
branch="${2:-$(git -C "$here" branch --show-current)}"
dir="$(mktemp -d)"
trap 'rm -rf "$dir"' EXIT
step() { printf '\n== %s\n' "$1"; }
fail() { printf '\nFAIL: %s\n' "$1"; exit 1; }

step "clone $branch"
git clone --quiet --depth 1 --branch "$branch" "$src" "$dir/repo" || fail "clone"
cd "$dir/repo"
step "backend install"
python3 -m venv .venv && . .venv/bin/activate || fail "venv"
pip install --quiet -e "backend[dev]" pyyaml || fail "pip install"
step "backend lint";  make lint >/dev/null || fail "make lint"
step "backend tests"; make test | tail -1 || fail "make test"
step "web install";   (cd web && npm ci --silent) || fail "npm ci"
step "web lint";      (cd web && npm run lint --silent) || fail "npm run lint"
step "web build";     (cd web && npm run build --silent >/dev/null) || fail "npm run build"
printf '\nPASS: clean clone of %s installs, lints, tests and builds\n' "$branch"

#!/usr/bin/env bash
# scripts/sandbox-run.sh - the ONLY place student code is allowed to execute.
#
# This is the real security boundary (guard.sh is only defence in depth).
#
# Two corrections to section 7.3 of the design document:
#
# 1. `--read-only` alone makes ordinary projects crash for reasons unrelated to
#    quality: anything that opens a SQLite file, writes a log or uses a temp
#    file dies on a read-only filesystem. Grading "functionality" from such a
#    run punishes normal code. A tmpfs for /tmp and a writable scratch dir fix
#    that without giving up isolation - the repo mount itself stays read-only.
#
# 2. The exit codes distinguish "the program failed" from "we could not run the
#    program". With `--network none` a project with external dependencies CANNOT
#    be installed, and that must not be scored as a functionality failure. It is
#    evidence of UNVERIFIABLE, which is a different rubric outcome.
#
# Usage:
#   bash scripts/sandbox-run.sh <repo-dir> <command...>
#   bash scripts/sandbox-run.sh work/detyra-sudoku python main.py
#
# Exit codes (consumed by the Reviewer when scoring 'functionality'):
#   0  ran and exited cleanly            -> evidence FOR functionality
#   1  ran and exited non-zero           -> evidence AGAINST functionality
#   2  could not run (no Docker)         -> UNVERIFIABLE, raise a flag
#   3  unresolvable dependencies         -> UNVERIFIABLE, NOT a zero
#   4  timed out                         -> evidence AGAINST (possible hang)
#   64 usage error

set -uo pipefail

IMAGE="${SANDBOX_IMAGE:-python:3.12-slim}"
TIMEOUT="${SANDBOX_TIMEOUT:-30}"
MEMORY="${SANDBOX_MEMORY:-256m}"
CPUS="${SANDBOX_CPUS:-0.5}"

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <repo-dir> <command...>" >&2
  exit 64
fi

REPO="$1"; shift

if [[ ! -d "$REPO" ]]; then
  echo "sandbox: '$REPO' is not a directory" >&2
  exit 64
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "SANDBOX_UNAVAILABLE: docker is not installed." >&2
  echo "Functionality cannot be observed. Score it UNVERIFIABLE and flag for human review;" >&2
  echo "do NOT award 0 - absence of evidence is not evidence of absence." >&2
  exit 2
fi

# An installed CLI is not a usable sandbox. A denied socket or a stopped daemon
# makes `docker run` exit 1, which is indistinguishable from "the student's
# program failed" unless it is checked separately - so check it separately.
if ! docker info >/dev/null 2>&1; then
  echo "SANDBOX_UNAVAILABLE: the docker daemon is not reachable (socket denied or not running)." >&2
  echo "This is an environment fault, NOT a defect in the reviewed project." >&2
  echo "Score functionality UNVERIFIABLE and flag for human review; do NOT award 0." >&2
  exit 2
fi

# Dependencies cannot be fetched inside a network-less container. Detect the
# case explicitly instead of letting it surface as an import error that looks
# like broken student code.
if [[ -z "${SANDBOX_DEPS_PRESTAGED:-}" ]]; then
  for manifest in requirements.txt Pipfile pyproject.toml package.json go.mod Cargo.toml pom.xml; do
    if [[ -f "$REPO/$manifest" ]]; then
      vendored=0
      for d in "$REPO/node_modules" "$REPO/vendor" "$REPO/.venv" "$REPO/venv"; do
        [[ -d "$d" ]] && vendored=1
      done
      if [[ "$vendored" == 0 ]]; then
        echo "DEPS_UNAVAILABLE: ${manifest} declares external dependencies and the" >&2
        echo "sandbox has no network, so they cannot be installed." >&2
        echo "Score functionality UNVERIFIABLE, not 0. To grade it, pre-stage the" >&2
        echo "dependencies in a custom image and set SANDBOX_IMAGE +" >&2
        echo "SANDBOX_DEPS_PRESTAGED=1." >&2
        exit 3
      fi
    fi
  done
fi

ABS_REPO="$(cd "$REPO" && pwd)"

# --network none        no exfiltration, no downloads
# --read-only           immutable root filesystem
# --tmpfs               the writable scratch real programs need
# -v ...:ro             the student's code cannot be modified by itself
# --cap-drop ALL        no privileged operations
# --security-opt        no privilege escalation via setuid binaries
# --pids-limit          fork bombs cannot exhaust the host
# --user 1000:1000      never root inside the container
docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --tmpfs /scratch:rw,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --memory "$MEMORY" \
  --cpus "$CPUS" \
  --user 1000:1000 \
  -e HOME=/scratch \
  -e TMPDIR=/tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$ABS_REPO:/app:ro" \
  -w /app \
  "$IMAGE" \
  timeout --signal=KILL "$TIMEOUT" "$@"

status=$?

if [[ "$status" == 137 || "$status" == 124 ]]; then
  echo "TIMEOUT: killed after ${TIMEOUT}s." >&2
  exit 4
fi
if [[ "$status" == 125 || "$status" == 126 || "$status" == 127 ]]; then
  echo "SANDBOX_UNAVAILABLE: container or entrypoint could not start (docker exit ${status})." >&2
  echo "Score UNVERIFIABLE rather than 0." >&2
  exit 2
fi
[[ "$status" == 0 ]] && exit 0
exit 1

#!/usr/bin/env bash
# Bounded, descriptor-bound, owner-only persistence for clipboard history.
set -euo pipefail
exec python3 "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/history-io.py" "$@"

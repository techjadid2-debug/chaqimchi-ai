#!/usr/bin/env bash
# Eski automation uchun compatibility wrapper.
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
exec "$script_dir/install_sotqin.sh" "$@"

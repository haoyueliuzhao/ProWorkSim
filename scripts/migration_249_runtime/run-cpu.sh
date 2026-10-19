#!/usr/bin/env bash
# Convenience entry for the default CPU-only private runtime.
set -euo pipefail
for argument in "$@"; do
    if [[ $argument == --gpu ]]; then
        printf '%s\n' 'Use run.sh --gpu with explicit physical device indices for a newly authorized GPU job.' >&2
        exit 2
    fi
done
exec "$(dirname -- "${BASH_SOURCE[0]}")/run.sh" "$@"

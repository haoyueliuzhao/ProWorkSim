#!/usr/bin/env bash
# CPU-only trusted SDK/scorer runtime; project bind preserves active nested mounts.
set -euo pipefail
repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_root=/data0/zhuxinrui/proworksim-runtime
temporary_root=$(mktemp -d "$repository_root/runs/software-benchmark-v054/native-worker-tmp/trusted.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT
unshare --user --map-root-user --mount --fork \
    /bin/bash "$repository_root/tools/enter_benchmark_runtime_v054.sh" \
    "$runtime_root" /data0/zhuxinrui "$temporary_root" rw "" "" "$@"

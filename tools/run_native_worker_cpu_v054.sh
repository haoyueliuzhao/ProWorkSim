#!/usr/bin/env bash
# Dedicated CPU worker namespaces are established before any SDK import.
set -euo pipefail
if [[ ${1:-} == --inside ]]; then
    runtime_root=$2
    temporary_root=$3
    shift 3
    mount --make-rprivate /
    # This process is PID 1 in the new namespace; bind only this proc view into
    # the trusted interpreter stage, then the worker mounts its own root's proc.
    mount -t proc -o nosuid,nodev,noexec proc /proc
    exec /bin/bash "$runtime_root/enter-namespace.sh" \
        "$runtime_root" /data0/zhuxinrui "$temporary_root" rw "" "" "$@"
fi
repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_root=/data0/zhuxinrui/proworksim-runtime
temporary_parent="$repository_root/runs/software-benchmark-v054/native-worker-tmp"
mkdir -p "$temporary_parent"
temporary_root=$(mktemp -d "$temporary_parent/worker.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT
exec_args=(
    /usr/bin/env
    "PYTHONPATH=$repository_root/src:$repository_root/runs/software-benchmark-v054/native-sdk-overlay:$repository_root/runs/v016-sdk/upstream/openhands-tools"
    LITELLM_LOCAL_MODEL_COST_MAP=True PYTHON_DOTENV_DISABLED=1
    "$repository_root/runs/v016-sdk/resident-venv/bin/python" -B
    "$repository_root/src/proworksim/software_benchmark_native_worker_v054.py"
)
unshare --user --map-root-user --mount --net --pid --fork \
    /bin/bash "$repository_root/tools/run_native_worker_cpu_v054.sh" --inside \
    "$runtime_root" "$temporary_root" "${exec_args[@]}" "$@"

#!/usr/bin/env bash
# Trusted SDK controller with a private /testbed metadata view; tools use RPC.
set -euo pipefail
if [[ ${1:-} == --inside ]]; then
    runtime_root=$2
    actor_root=$3
    temporary_root=$4
    shift 4
    mount --make-rprivate /
    mount --bind "$actor_root/testbed" "$runtime_root/sysroot/testbed"
    repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
    exec /bin/bash "$repository_root/tools/enter_benchmark_runtime_v054.sh" \
        "$runtime_root" /data0/zhuxinrui "$temporary_root" rw "" "" "$@"
fi
runtime_root=$1
actor_root=$2
shift 2
repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
temporary_root=$(mktemp -d "$runtime_root/controller.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT
unshare --user --map-root-user --mount --fork \
    /bin/bash "$repository_root/tools/run_native_sdk_controller_v054.sh" --inside \
    "$runtime_root" "$actor_root" "$temporary_root" \
    /usr/bin/env \
    "PYTHONPATH=$repository_root/src:$repository_root/runs/software-benchmark-v054/native-sdk-overlay:$repository_root/runs/v016-sdk/upstream/openhands-tools" \
    LITELLM_LOCAL_MODEL_COST_MAP=True PYTHON_DOTENV_DISABLED=1 \
    "$repository_root/runs/v016-sdk/resident-venv/bin/python" -B "$@"

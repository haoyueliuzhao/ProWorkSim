#!/usr/bin/env bash
# Original numeric ownership, mapped into the owner's existing subordinate IDs.
set -euo pipefail
repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --inside ]]; then
    runtime_root=$2
    temporary_root=$3
    shift 3
    mount --make-rprivate /
    mount -t proc -o nosuid,nodev,noexec proc /proc
    exec /bin/bash "$repository_root/tools/enter_benchmark_runtime_v054.sh" \
        "$runtime_root" /data0/zhuxinrui "$temporary_root" rw "" "" "$@"
fi
runtime_root=/data0/zhuxinrui/proworksim-runtime
arguments=("$@")
environment_manifest=
rootfs=
for ((index=0; index<${#arguments[@]}; index++)); do
    case ${arguments[index]} in
        --environment-manifest) environment_manifest=${arguments[index+1]:-} ;;
        --rootfs) rootfs=${arguments[index+1]:-} ;;
    esac
done
[[ -n "$environment_manifest" && -n "$rootfs" ]] || {
    printf '%s\n' 'A pinned rootfs and public environment manifest are required.' >&2
    exit 2
}
temporary_parent="$repository_root/runs/software-benchmark-v055/native-worker-tmp"
mkdir -p "$temporary_parent"
temporary_root=$(mktemp -d "$temporary_parent/mapped.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT
sudo -n /usr/bin/python3 "$repository_root/tools/native_uid_bootstrap_v055.py" launch \
    --environment-manifest "$environment_manifest" --rootfs "$rootfs" -- \
    /usr/bin/unshare --mount --net --pid --fork \
    /bin/bash "$repository_root/tools/run_native_worker_mapped_v055.sh" --inside \
    "$runtime_root" "$temporary_root" \
    /usr/bin/env \
    "PYTHONPATH=$repository_root/src:$repository_root/runs/software-benchmark-v054/native-sdk-overlay:$repository_root/runs/v016-sdk/upstream/openhands-tools" \
    LITELLM_LOCAL_MODEL_COST_MAP=True PYTHON_DOTENV_DISABLED=1 \
    "$repository_root/runs/v016-sdk/resident-venv/bin/python" -B \
    "$repository_root/src/proworksim/software_benchmark_native_worker_v054.py" "$@"

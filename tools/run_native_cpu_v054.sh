#!/usr/bin/env bash
# CPU-only companion to the existing private Python runtime, with a private PTY.
# This is a trusted construction/preparation launcher, not an actor sandbox.
set -euo pipefail

if [[ ${1:-} == --inside ]]; then
    runtime_root=$2
    data_root=$3
    temporary_root=$4
    shift 4
    sysroot=$runtime_root/sysroot
    mount --make-rprivate /
    # The inherited runtime deliberately has no PTY. Mount a new /dev view in
    # this namespace so no paths or device nodes are added to its shared sysroot.
    mount -t tmpfs -o mode=755,nosuid tmpfs "$sysroot/dev"
    for name in null zero random urandom; do
        touch "$sysroot/dev/$name"
    done
    mkdir "$sysroot/dev/pts"
    mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$sysroot/dev/pts"
    ln -s pts/ptmx "$sysroot/dev/ptmx"
    ln -s /proc/self/fd "$sysroot/dev/fd"
    ln -s /proc/self/fd/0 "$sysroot/dev/stdin"
    ln -s /proc/self/fd/1 "$sysroot/dev/stdout"
    ln -s /proc/self/fd/2 "$sysroot/dev/stderr"
    # Reuse the existing CPU mount/environment policy. Empty GPU arguments are
    # mandatory: this entry has no GPU option and never exposes NVIDIA devices.
    exec /bin/bash "$runtime_root/enter-namespace.sh" \
        "$runtime_root" "$data_root" "$temporary_root" rw "" "" "$@"
fi

repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_root=${PROWORKSIM_RUNTIME_ROOT:-/data0/zhuxinrui/proworksim-runtime}
data_root=${PROWORKSIM_DATA_ROOT:-/data0/zhuxinrui}
if (( $# == 0 )); then
    printf 'Usage: %s COMMAND [ARG ...]\n' "$0" >&2
    exit 2
fi
[[ -x "$runtime_root/sysroot/usr/bin/python3.12" ]]
[[ -f "$runtime_root/enter-namespace.sh" ]]
mkdir -p "$repository_root/runs/software-benchmark-v054/native-runtime-tmp"
temporary_root=$(mktemp -d "$repository_root/runs/software-benchmark-v054/native-runtime-tmp/cpu.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT
unshare --user --map-root-user --mount --fork \
    /bin/bash "$repository_root/tools/run_native_cpu_v054.sh" --inside \
    "$runtime_root" "$data_root" "$temporary_root" "$@"

#!/usr/bin/env bash
# Private CPU-only PTY using the current mount policy; no shared runtime changes.
set -euo pipefail
repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --inside ]]; then
    runtime_root=$2
    temporary_root=$3
    shift 3
    sysroot=$runtime_root/sysroot
    mount --make-rprivate /
    mount -t tmpfs -o mode=755,nosuid tmpfs "$sysroot/dev"
    for name in null zero random urandom; do touch "$sysroot/dev/$name"; done
    mkdir "$sysroot/dev/pts"
    mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$sysroot/dev/pts"
    ln -s pts/ptmx "$sysroot/dev/ptmx"
    ln -s /proc/self/fd "$sysroot/dev/fd"
    ln -s /proc/self/fd/0 "$sysroot/dev/stdin"
    ln -s /proc/self/fd/1 "$sysroot/dev/stdout"
    ln -s /proc/self/fd/2 "$sysroot/dev/stderr"
    exec /bin/bash "$repository_root/tools/enter_benchmark_runtime_v054.sh" \
        "$runtime_root" /data0/zhuxinrui "$temporary_root" rw "" "" "$@"
fi
runtime_root=/data0/zhuxinrui/proworksim-runtime
temporary_parent="$repository_root/runs/software-benchmark-v055/qualification-runtime-tmp"
mkdir -p "$temporary_parent"
temporary_root=$(mktemp -d "$temporary_parent/cpu.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT
unshare --user --map-root-user --mount --fork \
    /bin/bash "$repository_root/tools/run_deepseek_qualification_cpu_v055.sh" \
    --inside "$runtime_root" "$temporary_root" "$@"

#!/usr/bin/env bash
# A private shared-memory mount for the trusted REF service; never an actor mount.
set -euo pipefail
runtime_root=/data0/zhuxinrui/proworksim-runtime
repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --inside ]]; then
    shift
    mount --make-rprivate /
    toolchain_root="$repository_root/runs/software-benchmark-v054/ref-toolchain"
    [[ -x "$toolchain_root/usr/bin/gcc" && -f "$toolchain_root/usr/include/python3.12/Python.h" ]]
    temporary_root=$(mktemp -d "$repository_root/runs/software-benchmark-v054/ref-toolchain-work.XXXXXXXX")
    mkdir "$temporary_root/upper" "$temporary_root/work"
    # Existing runtime libraries take precedence. Only missing compiler,
    # headers and linker files are supplied by the authenticated overlay.
    mount -t overlay overlay -o "lowerdir=$runtime_root/sysroot/usr:$toolchain_root/usr,upperdir=$temporary_root/upper,workdir=$temporary_root/work" "$runtime_root/sysroot/usr"
    # Extracted APT packages do not run update-alternatives. Supply only the
    # standard compiler aliases in this disposable overlay, never on the host.
    ln -sfn /usr/bin/gcc "$runtime_root/sysroot/usr/bin/cc"
    ln -sfn /usr/bin/g++ "$runtime_root/sysroot/usr/bin/c++"
    # Reuse the matching installed CUDA 13 compiler in this private namespace.
    # Runtime driver SONAMEs still come from the explicit GPU launcher.
    cuda_toolchain=/usr/local/cuda-13.0
    [[ -x "$cuda_toolchain/bin/nvcc" && -f "$cuda_toolchain/include/cuda_runtime.h" ]]
    mkdir -p "$runtime_root/sysroot$cuda_toolchain"
    mount --bind "$cuda_toolchain" "$runtime_root/sysroot$cuda_toolchain"
    mount -o remount,bind,ro,nosuid,nodev "$runtime_root/sysroot$cuda_toolchain"
    mount -t tmpfs -o nosuid,nodev,size=16m,mode=755 tmpfs "$runtime_root/sysroot/dev"
    for device in null zero random urandom; do touch "$runtime_root/sysroot/dev/$device"; done
    mkdir "$runtime_root/sysroot/dev/shm"
    mount -t tmpfs -o nosuid,nodev,size=16g,mode=1777 tmpfs "$runtime_root/sysroot/dev/shm"
    exec "$repository_root/tools/run_benchmark_runtime_v054.sh" "$@"
fi
exec unshare --user --map-root-user --mount --fork /bin/bash "$0" --inside "$@"

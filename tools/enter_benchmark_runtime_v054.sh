#!/usr/bin/env bash
# v054 trusted runtime: preserve nested private Docker mounts during project bind.
set -euo pipefail
runtime_root=$1
data_root=$2
temporary_root=$3
project_mode=$4
gpu_devices=$5
gpu_uuids=$6
shift 6
sysroot=$runtime_root/sysroot
mount --make-rprivate /
bind_path() {
    local source_path=$1 destination_path=$2 mode=$3
    if [[ $source_path == "$data_root/projects/ProWorkSim" ]]; then
        mount --rbind "$source_path" "$destination_path"
    else
        mount --bind "$source_path" "$destination_path"
    fi
    if [[ $mode == ro ]]; then mount -o remount,bind,ro "$destination_path"; fi
}
# Separate bind points preserve /data1 identity after realpath/Path.resolve,
# while all physical data remains under /data0 on the destination host.
for disk_path in data1 data0; do
    bind_path "$data_root/projects/ProWorkSim" "$sysroot/$disk_path/zhuxinrui/projects/ProWorkSim" "$project_mode"
    for path in miniconda3 .local/lib/python3.14/site-packages models .cache/huggingface; do
        if [[ -d "$data_root/$path" ]]; then
            bind_path "$data_root/$path" "$sysroot/$disk_path/zhuxinrui/$path" ro
        fi
    done
done
if [[ -d "$data_root/.local/lib/python3.14/site-packages" ]]; then
    bind_path "$data_root/.local/lib/python3.14/site-packages" "$sysroot/home/zhuxinrui/.local/lib/python3.14/site-packages" ro
fi
if [[ -d "$data_root/.cache/huggingface" ]]; then
    bind_path "$data_root/.cache/huggingface" "$sysroot/home/zhuxinrui/.cache/huggingface" ro
fi
# /proc may contain protected automounts (e.g. binfmt_misc). A nonrecursive
# bind drops those submounts and is rejected in an unprivileged namespace.
# Preserve the existing tree and the kernel filesystem's locked flags.
mount --rbind /proc "$sysroot/proc"
proc_mode=ro
if [[ -n $gpu_devices ]]; then
    # CUDA initializes thread names via /proc/self/task/*/comm. Keep proc
    # writable only in this trusted GPU runtime; business sandboxes hide proc.
    [[ -n $gpu_uuids ]] || { printf '%s\n' 'Missing resolved GPU UUIDs.' >&2; exit 1; }
    proc_mode=rw
fi
mount -o "remount,bind,$proc_mode,nosuid,nodev,noexec" "$sysroot/proc"
for name in null zero random urandom; do
    bind_path "/dev/$name" "$sysroot/dev/$name" rw
done
bind_path "$temporary_root" "$sysroot/tmp" rw
for name in hosts resolv.conf; do
    bind_path "/etc/$name" "$sysroot/etc/$name" ro
done
driver_library_path=
if [[ -n $gpu_devices ]]; then
    # Only target NVIDIA driver SONAMEs enter this library path; no host libc.
    mkdir "$temporary_root/driver-lib"
    /sbin/ldconfig -p | awk 'index($0, "x86-64") && $1 ~ /^(libcuda\.so|libnvidia-)/ && $(NF-1) == "=>" {print $1, $NF}' \
        > "$temporary_root/driver-bindings.tsv"
    while read -r soname source_path; do
        [[ -f $source_path && ! -e "$temporary_root/driver-lib/$soname" ]] || continue
        : > "$temporary_root/driver-lib/$soname"
        bind_path "$source_path" "$temporary_root/driver-lib/$soname" ro
    done < "$temporary_root/driver-bindings.tsv"
    [[ -f "$temporary_root/driver-lib/libcuda.so.1" ]] || {
        printf '%s\n' 'Target libcuda.so.1 not found; refusing GPU launch.' >&2
        exit 1
    }
    mount --rbind "$temporary_root/driver-lib" "$sysroot/opt/host-nvidia"
    driver_library_path=/opt/host-nvidia
    IFS=, read -r -a selected_devices <<< "$gpu_devices"
    for index in "${selected_devices[@]}"; do
        [[ -c /dev/nvidia$index ]] || { printf 'Missing GPU device: %s\n' "$index" >&2; exit 1; }
        touch "$sysroot/dev/nvidia$index"
        bind_path "/dev/nvidia$index" "$sysroot/dev/nvidia$index" rw
    done
    for name in nvidiactl nvidia-uvm nvidia-uvm-tools; do
        if [[ -c /dev/$name ]]; then
            touch "$sysroot/dev/$name"
            bind_path "/dev/$name" "$sysroot/dev/$name" rw
        fi
    done
    if [[ -x /usr/bin/nvidia-smi ]]; then
        touch "$sysroot/usr/bin/nvidia-smi"
        bind_path /usr/bin/nvidia-smi "$sysroot/usr/bin/nvidia-smi" ro
    fi
    mount --rbind /sys "$sysroot/sys"
    mount -o remount,bind,ro,nosuid,nodev,noexec "$sysroot/sys"
fi
exec /usr/sbin/chroot "$sysroot" /usr/bin/env -i \
    HOME=/home/zhuxinrui USER=zhuxinrui LOGNAME=zhuxinrui \
    PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TMPDIR=/tmp \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/data1/zhuxinrui/projects/ProWorkSim/src \
    CUDA_VISIBLE_DEVICES="$gpu_uuids" NVIDIA_VISIBLE_DEVICES="${gpu_uuids:-void}" \
    PROWORKSIM_HOST_GPU_DEVICES="$gpu_devices" \
    LD_LIBRARY_PATH="$driver_library_path" \
    /bin/sh -c 'cd /data1/zhuxinrui/projects/ProWorkSim && exec "$@"' migration-runtime "$@"

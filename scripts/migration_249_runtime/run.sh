#!/usr/bin/env bash
# Private source-host Python runtime; CPU by default. Target GPU devices and
# target driver libraries are available only through an explicit --gpu list.
set -euo pipefail

runtime_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
data_root=${PROWORKSIM_DATA_ROOT:-/data0/zhuxinrui}
project_mode=ro
gpu_devices=
while (( $# )); do
    case "$1" in
        --write-project) project_mode=rw; shift ;;
        --gpu)
            gpu_devices=${2:-}
            if [[ ! $gpu_devices =~ ^(0|[1-9][0-9]*)(,(0|[1-9][0-9]*))*$ ]]; then
                printf '%s\n' '--gpu requires explicit physical indices, e.g. 0,1.' >&2
                exit 2
            fi
            shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if (( $# == 0 )); then
    printf 'Usage: %s [--write-project] [--gpu 0,1] [--] COMMAND [ARG ...]\n' "$0" >&2
    printf 'Example: %s /data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python -B -c "import proworksim"\n' "$0" >&2
    exit 2
fi
gpu_uuids=
if [[ -n $gpu_devices ]]; then
    # CUDA enumeration inside the restricted /dev view need not preserve host
    # indices. Resolve and validate identity on the host before any namespace.
    command -v nvidia-smi >/dev/null || {
        printf '%s\n' 'nvidia-smi unavailable; refusing GPU launch.' >&2
        exit 1
    }
    declare -A seen_devices=() seen_uuids=()
    IFS=, read -r -a selected_devices <<< "$gpu_devices"
    for index in "${selected_devices[@]}"; do
        if [[ -v seen_devices[$index] ]]; then
            printf 'Duplicate physical GPU index: %s\n' "$index" >&2
            exit 1
        fi
        seen_devices[$index]=1
        if ! identity=$(nvidia-smi --id="$index" --query-gpu=index,uuid --format=csv,noheader,nounits); then
            printf 'Cannot resolve physical GPU index: %s\n' "$index" >&2
            exit 1
        fi
        identity=${identity//[[:blank:]]/}
        if [[ ! $identity =~ ^${index},(GPU-[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12})$ ]]; then
            printf 'Invalid GPU identity for physical index %s; refusing GPU launch.\n' "$index" >&2
            exit 1
        fi
        uuid=${BASH_REMATCH[1]}
        if [[ -v seen_uuids[$uuid] ]]; then
            printf 'Duplicate GPU UUID for physical index %s; refusing GPU launch.\n' "$index" >&2
            exit 1
        fi
        seen_uuids[$uuid]=1
        gpu_uuids+="${gpu_uuids:+,}$uuid"
    done
fi
[[ -f "$runtime_root/manifest.json" && -x "$runtime_root/sysroot/usr/bin/python3.12" ]]
[[ -d "$data_root/projects/ProWorkSim" ]]
temporary_root=$(mktemp -d "$runtime_root/tmp/cpu.XXXXXXXX")
trap 'rm -rf -- "$temporary_root"' EXIT

# The host's bash/mount/chroot run before chroot with the target libc.  Only
# children inside the private sysroot see the source Python and source libc.
unshare --user --map-root-user --mount --fork /bin/bash "$runtime_root/enter-namespace.sh" \
    "$runtime_root" "$data_root" "$temporary_root" "$project_mode" "$gpu_devices" "$gpu_uuids" "$@"

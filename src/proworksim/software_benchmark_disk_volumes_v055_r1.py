"""Account future disk growth separately on two explicitly registered volumes.

Only future DeepSeek generation directories may use the secondary mount. Qwen,
preparation, shared templates, Docker grading, the queue and cash ledger remain
on primary. Mount loss or ambiguous placement never falls back silently.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat

from . import software_benchmark_disk_stages_v055_r1 as stages
from .software_benchmark_candidates_v054 import checked
from .software_benchmark_queue_v055 import ROOT, load, now

VERSION = "v055-device-bound-two-volume-disk-r1"
POLICY = stages.POLICY
STAGE_POLICY = stages.STAGE_POLICY
SECONDARY_ROOT = ROOT / "runs/software-benchmark-v055/secondary-volume-r1"
SOURCE_ROOT = Path("/data1/proworksim-zhuxinrui/v055-worker-volume-r1")
VOLUME_POLICY = {"version": VERSION, "default_target": "primary",
    "future_deepseek_generations": "secondary", "legacy_qwen_generations": "primary",
    "preparation_and_shared_cache": "primary", "Docker_grading_and_ledger": "primary",
    "unknown_placement_blocks_dispatch": True, "mount_loss_fallback": False,
    "active_placement_uses_observed_st_dev": True, "inflight_directories_moved": False}
disk_dispatch_lock = stages.disk_dispatch_lock
admission = stages.admission
generation_estimate = stages.generation_estimate
_VOLUME_REF = None
_VOLUME = None


def _mount_key(line):
    fields = line.split()
    separator = fields.index("-")
    return (fields[2], fields[3], fields[4], fields[separator + 1], fields[separator + 2])


def _live_identity(volume, *, mountinfo=None):
    primary, secondary, source = ROOT, SECONDARY_ROOT, SOURCE_ROOT
    if (volume.get("version") != "v055-secondary-worker-volume-r1"
            or volume.get("primary_path") != str(primary)
            or volume.get("project_mountpoint") != str(secondary)
            or volume.get("source_directory") != str(source)
            or volume.get("mounted") is not True
            or volume.get("existing_data_moved") is not False
            or volume.get("inflight_paths_modified") is not False
            or volume.get("device_identity_must_match_on_dispatch") is not True):
        raise ValueError("Unrecognized explicitly registered secondary volume")
    for path in (primary, secondary, source):
        if path.resolve() != path or not path.is_dir():
            raise ValueError("Registered volume path changed or became a symlink")
    old, new, real = primary.stat(), secondary.stat(), source.stat()
    if (old.st_dev != volume["primary_device"] or new.st_dev != volume["secondary_device"]
            or real.st_dev != new.st_dev or new.st_dev == old.st_dev
            or (new.st_ino, new.st_uid, new.st_gid) != (real.st_ino, real.st_uid, real.st_gid)
            or new.st_uid != volume["owner_uid"] or new.st_gid != volume["owner_gid"]):
        raise ValueError("Primary/secondary device, source inode or ownership changed")
    marker = volume["marker"]
    if marker["path"] != str(secondary / "volume-identity.json"):
        raise ValueError("Volume marker escaped the registered mount")
    info = Path(marker["path"]).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_dev != new.st_dev:
        raise ValueError("Volume marker is not a regular secondary-volume file")
    value = json.loads(checked(marker).read_bytes())
    if value.get("uuid") != volume["uuid"]:
        raise ValueError("Volume marker UUID changed")
    text = Path("/proc/self/mountinfo").read_text() if mountinfo is None else mountinfo
    found = [line for line in text.splitlines() if len(line.split()) > 4 and line.split()[4] == str(secondary)]
    if len(found) != 1 or _mount_key(found[0]) != _mount_key(volume["mountinfo_line"]):
        raise ValueError("Exact secondary bind-mount source/device identity is absent")
    return {"primary": {"path": str(primary), "device": old.st_dev},
            "secondary": {"path": str(secondary), "device": new.st_dev,
                          "source_directory": str(source), "uuid": volume["uuid"]}}


def configure(reference):
    """One immutable volume binding per dedicated coordinator process."""
    global _VOLUME_REF, _VOLUME
    if _VOLUME_REF is not None and _VOLUME_REF != reference:
        raise ValueError("A process cannot switch registered volumes")
    volume = load(reference)
    identity = _live_identity(volume)
    _VOLUME_REF, _VOLUME = dict(reference), volume
    return {"registration": _VOLUME_REF, "identity": identity}


def _placement(record, *, family, volumes):
    key = "worker_directory" if family == "v054" else "directory"
    path = Path(record[key])
    allowed = ROOT / ("runs/software-benchmark-v054" if family == "v054" else "runs/software-benchmark-v055")
    if path.resolve() != path or not path.is_dir() or not path.is_relative_to(allowed):
        raise ValueError("Active worker directory is missing or outside its experiment")
    label = "secondary" if path.is_relative_to(SECONDARY_ROOT) else "primary"
    if family == "v054" and label != "primary":
        raise ValueError("Qwen must retain its original primary placement")
    observed = path.stat().st_dev
    if observed != volumes[label]["device"]:
        raise ValueError("Active worker path and actual filesystem device disagree")
    return label, {"worker_directory": str(path), "device": observed}


def partition_snapshot(snapshot, v054_state, v055_state, volumes, *, placement=_placement):
    """Keep target-volume accounting separate; unknown placement blocks both."""
    grouped = {name: {**value, "active_reservations": [], "active_peak_reserved_bytes": 0}
               for name, value in volumes.items()}
    errors = []
    lookup = {"v054": {row["slot"]["slot_id"]: row for row in v054_state["rows"]},
              "v055": {row["slot"]["slot_id"]: row for row in v055_state["rows"]}}
    for family, field in (("v054", "v054_generations"), ("v055", "v055_generations")):
        for item in snapshot[field]:
            try:
                label, proof = placement(lookup[family][item["slot_id"]]["generation"], family=family, volumes=volumes)
                grouped[label]["active_reservations"].append({**item, "volume": label, "placement": proof})
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append({"slot_id": item.get("slot_id"), "type": type(error).__name__, "message": str(error)})
                # Admission is blocked; conservatively show the amount on both
                # volumes rather than interpreting an unreadable path as zero.
                for label in grouped:
                    grouped[label]["active_reservations"].append({**item, "volume": "unknown"})
    for item in snapshot["v055_preparations"]:
        try:
            worker = v055_state["preparation"][item["instance_id"]]["worker"]
            label, proof = placement(worker, family="v055", volumes=volumes)
            cache = ROOT / "runs/software-benchmark-v054/native-lazy-cache"
            if label != "primary" or cache.stat().st_dev != volumes["primary"]["device"]:
                raise ValueError("Preparation worker or shared cache left the primary volume")
            grouped["primary"]["active_reservations"].append({**item, "volume": "primary", "placement": proof})
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append({"instance_id": item.get("instance_id"), "type": type(error).__name__, "message": str(error)})
            for label in grouped:
                grouped[label]["active_reservations"].append({**item, "volume": "unknown"})
    for value in grouped.values():
        value["active_peak_reserved_bytes"] = sum(row["peak_bytes"] for row in value["active_reservations"])
    return grouped, errors


def shared_disk_snapshot(*, v055_state=None, v054_state=None, cache=None, target_volume="primary"):
    """Call under the shared dispatch lock; default remains Qwen's primary disk."""
    if target_volume not in {"primary", "secondary"}:
        raise ValueError("Unknown target volume")
    try:
        if _VOLUME_REF is None:
            raise ValueError("The secondary volume has not been explicitly configured")
        # Re-read the SHA-bound registration as well as checking live devices.
        volume = load(_VOLUME_REF)
        identities = _live_identity(volume)
        if v054_state is None:
            v054_state = json.loads((ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json").read_bytes())
        if v055_state is None:
            v055_state = json.loads((ROOT / "runs/software-benchmark-v055/queue-r1/state.json").read_bytes())
        snapshot = stages.shared_disk_snapshot(v054_state=v054_state, v055_state=v055_state, cache=cache)
        grouped, errors = partition_snapshot(snapshot, v054_state, v055_state, identities)
        for value in grouped.values():
            value["free_bytes"] = shutil.disk_usage(value["path"]).free
        selected = grouped[target_volume]
        error = snapshot["metadata_error"]
        if errors:
            error = {"scope": "volume_placement", "errors": errors}
        return {**snapshot, "volume_policy": VOLUME_POLICY, "volume_registration": _VOLUME_REF,
            "target_volume": target_volume, "volumes": grouped,
            "free_bytes": selected["free_bytes"],
            "active_peak_reserved_bytes": selected["active_peak_reserved_bytes"],
            "metadata_error": error, "volume_identity_verified_utc": now()}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"observed_utc": now(), "policy": POLICY, "stage_policy": STAGE_POLICY,
            "volume_policy": VOLUME_POLICY, "volume_registration": _VOLUME_REF,
            "target_volume": target_volume, "volumes": {}, "free_bytes": 0,
            "active_peak_reserved_bytes": 0, "v054_generations": [], "v055_generations": [],
            "v055_preparations": [], "metadata_error": {"scope": "volume_identity_or_observation",
                "type": type(error).__name__, "message": str(error)}, "silent_primary_fallback": False}

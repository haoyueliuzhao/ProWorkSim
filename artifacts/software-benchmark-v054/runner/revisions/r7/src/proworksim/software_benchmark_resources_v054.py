"""One aggregate actor CPU/memory/pid budget per episode, outside model serving."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

VERSION = "v054-episode-resource-slice-v2"
CLAIM = re.compile(r"[a-f0-9]{32}")


def _systemctl(*args):
    return subprocess.run(["systemctl", *args], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def inspect_resources(manifest):
    if (manifest.get("version") != VERSION or manifest.get("manager") != "system"
            or not CLAIM.fullmatch(manifest["claim_id"])):
        raise ValueError("An episode-owned resource manifest is required")
    name = "proworksimv054ep" + manifest["claim_id"] + ".slice"
    if manifest["slice"] != name:
        raise ValueError("Resource slice differs from episode identity")
    fields = _systemctl("show", name, "--property=Id,ControlGroup,ActiveState,InvocationID")
    state = dict(line.split("=", 1) for line in fields.splitlines() if "=" in line)
    if state["ActiveState"] != "active" or state["Id"] != name:
        raise ValueError("Episode resource slice is not active")
    if manifest.get("invocation_id") and manifest["invocation_id"] != state["InvocationID"]:
        raise ValueError("Episode resource slice was replaced")
    cgroup = state["ControlGroup"]
    if cgroup != "/" + name:
        raise ValueError("Unexpected resource cgroup")
    root = Path("/sys/fs/cgroup" + cgroup)
    actual = {name: (root / name).read_text().strip()
              for name in ("cpu.max", "memory.max", "pids.max")}
    quota, period = actual["cpu.max"].split()
    if (quota == "max" or int(quota) != 4 * int(period)
            or actual["memory.max"] != str(16 * 1024**3) or actual["pids.max"] != "16384"):
        raise ValueError("Aggregate actor resource limits differ from the frozen contract")
    return {"version": VERSION, "manager": "system", "claim_id": manifest["claim_id"], "slice": name,
            "invocation_id": state["InvocationID"], "cgroup": cgroup,
            "kernel_limits": actual, "cpu_count": 4, "memory_bytes": 16 * 1024**3,
            "pids_limit": 16384, "scope": "controller+actor+all public test descendants",
            "model_service_included": False}


def create_episode_resources(claim_id, directory):
    if not CLAIM.fullmatch(claim_id):
        raise ValueError("Invalid episode claim")
    path = Path(directory) / "resource-slice.json"
    if path.exists():
        raise FileExistsError("Episode resources cannot silently be reused")
    name = "proworksimv054ep" + claim_id + ".slice"
    helper = Path(__file__).resolve().parents[2] / "tools/native_resource_helper_v054.py"
    subprocess.run(["sudo", "-n", "/usr/bin/python3", str(helper), "create", claim_id],
                   check=True, capture_output=True, text=True, timeout=40)
    manifest = inspect_resources({"version": VERSION, "manager": "system",
                                  "claim_id": claim_id, "slice": name})
    with path.open("x") as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return manifest


def assert_member(manifest, cgroup):
    current = inspect_resources(manifest)
    if not cgroup.startswith(current["cgroup"] + "/"):
        raise ValueError("Episode process is outside the common actor resource slice")
    return current


def release_episode_resources(manifest):
    current = inspect_resources(manifest)
    root = Path("/sys/fs/cgroup" + current["cgroup"])
    events = dict(line.split() for line in (root / "cgroup.events").read_text().splitlines())
    if events.get("populated") != "0":
        raise RuntimeError("Cannot release resources while an episode descendant is alive")
    helper = Path(__file__).resolve().parents[2] / "tools/native_resource_helper_v054.py"
    subprocess.run(["sudo", "-n", "/usr/bin/python3", str(helper), "release",
                    current["claim_id"], "--invocation", current["invocation_id"]],
                   check=True, capture_output=True, text=True, timeout=40)
    return {"slice": current["slice"], "populated": False, "released": True}

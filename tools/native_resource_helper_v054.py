"""Finite project-only system-slice bootstrap; never changes user@ or ancestors."""
import argparse
import os
from pathlib import Path
import re
import subprocess


def command(*args):
    return subprocess.run(["systemctl", *args], check=True, capture_output=True,
                          text=True, timeout=30).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "release"])
    parser.add_argument("claim")
    parser.add_argument("--invocation")
    args = parser.parse_args()
    if (os.geteuid() != 0 or os.environ.get("SUDO_UID") != "1021"
            or not re.fullmatch(r"[a-f0-9]{32}", args.claim)):
        raise PermissionError("Only the registered owner can manage its episode resource slice")
    unit = "proworksimv054ep" + args.claim + ".slice"
    if args.operation == "create":
        existing = command("show", unit, "--property=ActiveState,InvocationID")
        if "ActiveState=active" in existing:
            raise FileExistsError("A live episode resource slice cannot be reused")
        command("set-property", "--runtime", unit, "CPUQuota=400%",
                "MemoryMax=17179869184", "TasksMax=16384")
        command("start", unit)
    else:
        actual = dict(line.split("=", 1) for line in command(
            "show", unit, "--property=ControlGroup,InvocationID").splitlines() if "=" in line)
        if (actual["InvocationID"] != args.invocation
                or actual["ControlGroup"] != "/" + unit):
            raise ValueError("Resource slice invocation differs")
        events = dict(line.split() for line in Path(
            "/sys/fs/cgroup/" + unit + "/cgroup.events").read_text().splitlines())
        if events.get("populated") != "0":
            raise RuntimeError("Cannot remove resource limits of a live episode")
        command("stop", unit)
        command("revert", unit)


if __name__ == "__main__":
    main()

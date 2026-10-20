"""No-GPU controls for physical identity mapping and trusted proc mount policy."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "migration_249_runtime"
UUID3 = "GPU-7e01944c-768c-2f33-d58e-85d9b62ee185"
UUID7 = "GPU-39eb51c7-179a-1aa6-0735-2e33652bb7b8"


def executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


@pytest.fixture
def launcher(tmp_path):
    runtime = tmp_path / "runtime"
    binary = tmp_path / "bin"
    data = tmp_path / "data"
    binary.mkdir()
    (runtime / "sysroot/usr/bin").mkdir(parents=True)
    (runtime / "tmp").mkdir()
    (data / "projects/ProWorkSim").mkdir(parents=True)
    (runtime / "manifest.json").write_text("{}")
    executable(runtime / "sysroot/usr/bin/python3.12", "#!/bin/sh\nexit 0\n")
    shutil.copy2(SOURCE / "run.sh", runtime / "run.sh")
    capture = tmp_path / "unshare.json"
    executable(
        binary / "unshare",
        f"#!{sys.executable}\nimport json, os, sys\n"
        "open(os.environ['CAPTURE'], 'w').write(json.dumps(sys.argv[1:]))\n",
    )
    # The migrated CPU sysroot intentionally contains only required binaries.
    executable(
        binary / "mktemp",
        f"#!{sys.executable}\nimport pathlib, sys, tempfile\n"
        "p=pathlib.Path(sys.argv[-1])\n"
        "print(tempfile.mkdtemp(prefix=p.name.rstrip('X'), dir=p.parent))\n",
    )
    executable(
        binary / "rm",
        f"#!{sys.executable}\nimport shutil, sys\nshutil.rmtree(sys.argv[-1])\n",
    )
    executable(
        binary / "nvidia-smi",
        "#!/bin/bash\n"
        'if [[ ${IDENTITY_MODE:-valid} == failed ]]; then exit 1; fi\n'
        'if [[ ${IDENTITY_MODE:-valid} == malformed ]]; then echo 3,GPU-bad; exit; fi\n'
        'if [[ ${IDENTITY_MODE:-valid} == mismatch ]]; then echo 7,'
        + UUID7
        + "; exit; fi\n"
        'if [[ ${IDENTITY_MODE:-valid} == multiline ]]; then printf "3,'
        + UUID3
        + '\\n7,'
        + UUID7
        + '\\n"; exit; fi\n'
        'case "$1" in\n'
        f" --id=3) echo '3, {UUID3}' ;;\n"
        f" --id=7) echo '7, {UUID7}' ;;\n"
        " *) exit 1 ;;\nesac\n",
    )
    env = {
        **os.environ,
        "PATH": f"{binary}:/usr/bin:/bin",
        "PROWORKSIM_DATA_ROOT": str(data),
        "CAPTURE": str(capture),
    }
    return runtime, binary, data, capture, env


def test_explicit_gpu_order_maps_to_uuids(launcher):
    runtime, _, _, capture, env = launcher
    result = subprocess.run(
        [str(runtime / "run.sh"), "--gpu", "7,3", "--", "true"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    args = json.loads(capture.read_text())
    assert args[-3:] == ["7,3", f"{UUID7},{UUID3}", "true"]


def test_cpu_does_not_query_gpu(launcher):
    runtime, _, _, capture, env = launcher
    result = subprocess.run(
        [str(runtime / "run.sh"), "true"],
        env={**env, "IDENTITY_MODE": "failed"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text())[-3:] == ["", "", "true"]


@pytest.mark.parametrize(
    ("selection", "identity_mode"),
    [
        ("3", "failed"),
        ("3", "malformed"),
        ("3", "mismatch"),
        ("3", "multiline"),
        ("3,3", "valid"),
        ("03", "valid"),
        ("8", "valid"),
    ],
)
def test_invalid_identity_never_enters_namespace(launcher, selection, identity_mode):
    runtime, _, _, capture, env = launcher
    result = subprocess.run(
        [str(runtime / "run.sh"), "--gpu", selection, "true"],
        env={**env, "IDENTITY_MODE": identity_mode},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not capture.exists()


@pytest.mark.parametrize(("devices", "uuids", "mode"), [("", "", "ro"), ("3", UUID3, "rw")])
def test_proc_policy_without_real_mounts(launcher, devices, uuids, mode):
    runtime, binary, data, _, env = launcher
    log = runtime / "mount-log"
    executable(
        binary / "mount",
        '#!/bin/bash\nprintf "%s\\n" "$*" >> "$MOUNT_LOG"\n'
        # Exit immediately after observing the proc remount, before GPU setup.
        '[[ "$*" == *remount,bind,* && "$*" == */proc ]] && exit 76\nexit 0\n',
    )
    result = subprocess.run(
        [
            "/bin/bash",
            str(SOURCE / "enter-namespace.sh"),
            str(runtime),
            str(data),
            str(runtime / "tmp"),
            "ro",
            devices,
            uuids,
            "true",
        ],
        env={**env, "MOUNT_LOG": str(log)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 76, result.stderr
    assert f"-o remount,bind,{mode},nosuid,nodev,noexec {runtime}/sysroot/proc" in log.read_text()

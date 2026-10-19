#!/usr/bin/env python3
"""Package the source host's Python 3.12 CPU runtime without changing it.

This migration utility is not an experiment runner.  It creates a new private
sysroot and records the source bytes; it never copies a project secret or an
NVIDIA device/driver.  Run it with the source system Python, not a model venv.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(destination: Path) -> dict:
    if destination.exists():
        raise FileExistsError(f"Use a new runtime destination: {destination}")
    destination.mkdir(parents=True)
    root = destination / "sysroot"
    root.mkdir()
    for name, target in {
        "bin": "usr/bin",
        "sbin": "usr/sbin",
        "lib": "usr/lib",
        "lib64": "usr/lib64",
    }.items():
        (root / target).mkdir(parents=True, exist_ok=True)
        (root / name).symlink_to(target)
    files = {}

    def copy_file(source: Path) -> None:
        # Preserve the requested absolute spelling: the private root has the
        # same /lib -> /usr/lib layout as the source host.
        target = root / source.relative_to("/")
        if target.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=True)
        files[str(source)] = {"sha256": sha256(source), "size": source.stat().st_size}

    stdlib = Path("/usr/lib/python3.12")
    shutil.copytree(stdlib, root / stdlib.relative_to("/"), symlinks=True)
    for path in stdlib.rglob("*"):
        if path.is_file():
            files[str(path)] = {"sha256": sha256(path), "size": path.stat().st_size}
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(stdlib):
                copy_file(resolved)
                # The source symlink may stop at an intermediate soname.
                link_target = path.parent / path.readlink()
                if link_target.is_absolute():
                    copy_file(Path(os.path.normpath(link_target)))

    business_tools = (
        "bash",
        "git",
        "rg",
        "timeout",
        "patch",
        "diff",
        "make",
        "tar",
        "gzip",
        "unzip",
        "bzip2",
        "xz",
        "find",
        "sed",
        "awk",
        "grep",
        "xargs",
        "wc",
        "sort",
        "cut",
        "tr",
        "head",
        "tail",
        "cat",
        "tee",
        "sha256sum",
        "cp",
        "mv",
        "rm",
        "mkdir",
        "rmdir",
        "touch",
        "ln",
        "pwd",
        "readlink",
        "realpath",
        "uname",
        "date",
        "sleep",
        "stat",
        "du",
        "df",
        "basename",
        "dirname",
        "seq",
        "true",
        "false",
        "ps",
        "pgrep",
        "kill",
        "nproc",
        "which",
    )
    git_roots = [Path("/usr/lib/git-core"), Path("/usr/share/git-core")]
    git_elf_files = []
    for git_root in git_roots:
        shutil.copytree(git_root, root / git_root.relative_to("/"), symlinks=True)
        for path in git_root.rglob("*"):
            if path.is_file():
                files[str(path)] = {"sha256": sha256(path), "size": path.stat().st_size}
                with path.open("rb") as stream:
                    if stream.read(4) == b"\x7fELF":
                        git_elf_files.append(path)
    initial = [
        Path("/usr/bin/python3.12"),
        Path("/usr/bin/dash"),
        Path("/usr/bin/env"),
        *[Path("/usr/bin") / name for name in business_tools],
        *git_elf_files,
        Path("/usr/lib/x86_64-linux-gnu/libstdc++.so.6"),
        Path("/usr/lib/x86_64-linux-gnu/libgcc_s.so.1"),
        Path("/usr/lib/x86_64-linux-gnu/libseccomp.so.2"),
        *[
            Path("/usr/lib/x86_64-linux-gnu") / name
            for name in ("libpthread.so.0", "libdl.so.2", "librt.so.1", "libutil.so.1")
        ],
        *sorted(stdlib.rglob("*.so")),
    ]
    pending = list(initial)
    seen = set()
    while pending:
        path = pending.pop()
        if str(path) in seen:
            continue
        seen.add(str(path))
        copy_file(path)
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        process = subprocess.run(["ldd", str(path)], check=False, text=True, capture_output=True)
        if process.returncode != 0:
            raise RuntimeError(f"Cannot inspect trusted runtime ELF {path}: {process.stderr}")
        if "not found" in process.stdout:
            raise RuntimeError(f"Unresolved source dependency: {path}\n{process.stdout}")
        for line in process.stdout.splitlines():
            match = re.search(r"(?:=>\s+)?(/\S+)\s+\(", line)
            if match:
                pending.append(Path(match.group(1)))
    (root / "usr/bin/python3").symlink_to("python3.12")
    (root / "usr/bin/sh").symlink_to("dash")
    for source in [
        Path("/etc/ssl/certs/ca-certificates.crt"),
        Path("/etc/python3.12/sitecustomize.py"),
    ]:
        if source.exists():
            copy_file(source)
    for relative in [
        "proc",
        "sys",
        "dev",
        "tmp",
        "etc",
        "opt/host-nvidia",
        "home/zhuxinrui/.local/lib/python3.14/site-packages",
        "data1/zhuxinrui/projects/ProWorkSim",
        "data1/zhuxinrui/miniconda3",
        "data1/zhuxinrui/.local/lib/python3.14/site-packages",
        "data1/zhuxinrui/models",
        "data1/zhuxinrui/.cache/huggingface",
        "data0/zhuxinrui/.cache/huggingface",
        "home/zhuxinrui/.cache/huggingface",
        "data0/zhuxinrui/projects/ProWorkSim",
        "data0/zhuxinrui/miniconda3",
        "data0/zhuxinrui/.local/lib/python3.14/site-packages",
        "data0/zhuxinrui/models",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative, target in {
        "home/zhuxinrui/datatmp": "/data1/zhuxinrui",
        "dev/fd": "/proc/self/fd",
        "dev/stdin": "/proc/self/fd/0",
        "dev/stdout": "/proc/self/fd/1",
        "dev/stderr": "/proc/self/fd/2",
    }.items():
        (root / relative).symlink_to(target)
    for name in ["null", "zero", "random", "urandom"]:
        (root / "dev" / name).touch()
    for name in ["hosts", "resolv.conf"]:
        (root / "etc" / name).touch()
    (root / "etc/passwd").write_text("root:x:0:0:Migration namespace:/home/zhuxinrui:/bin/sh\n")
    (root / "etc/group").write_text("root:x:0:\n")
    (root / "etc/nsswitch.conf").write_text("passwd: files\ngroup: files\nhosts: files dns\n")
    (root / "tmp").chmod(0o1777)
    helpers = Path(__file__).parent
    for name in ["run.sh", "run-cpu.sh", "enter-namespace.sh", "verify_cpu.py"]:
        shutil.copy2(helpers / name, destination / name)
        if name.endswith(".sh"):
            (destination / name).chmod(0o755)
    (destination / "tmp").mkdir(mode=0o700)
    manifest = {
        "version": "server-249-private-runtime-v4",
        "source_python": subprocess.check_output(
            ["/usr/bin/python3.12", "--version"], text=True
        ).strip(),
        "source_glibc": subprocess.check_output(["ldd", "--version"], text=True).splitlines()[0],
        "source_system": os.uname()._asdict()
        if hasattr(os.uname(), "_asdict")
        else list(os.uname()),
        "source_files": dict(sorted(files.items())),
        "source_business_tools": list(business_tools),
        "source_git_helper_trees": [str(path) for path in git_roots],
        "external_read_only_mounts": [
            "project",
            "miniconda3",
            "python3.14_user_site",
            "historical_models",
            "huggingface_cache",
        ],
        "host_usr_or_libraries_changed": False,
        "experiment_replay_equivalence_claimed": False,
        "model_or_gpu_execution": False,
        "optional_gpu_launcher_prepared_not_executed": True,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {
        "destination": str(destination),
        "source_file_count": len(files),
        "source_bytes": sum(row["size"] for row in files.values()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.destination.resolve()), indent=2))

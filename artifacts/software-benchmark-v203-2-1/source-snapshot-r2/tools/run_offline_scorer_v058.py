"""Launch the fixed scorer Python as an ordinary host process.

The existing private ELF loader supplies the matching libc without chroot,
mounts, namespaces, a shell, daemon management, or inherited LD_* settings.
This trusted-host launcher is not an actor sandbox or a grading authorization.
The v058 scoring entrypoints retain their own dispatch and Docker guards.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SYSROOT = Path("/data0/zhuxinrui/proworksim-runtime/sysroot")
VERSION = "v058-unprivileged-fixed-python-launcher-r1"


def layout(root=ROOT, sysroot=SYSROOT):
    root, sysroot = Path(root).resolve(), Path(sysroot).resolve()
    return {
        "root": root,
        "sysroot": sysroot,
        "loader": sysroot / "usr/lib64/ld-linux-x86-64.so.2",
        "python": sysroot / "usr/bin/python3.12",
        "python_home": sysroot / "usr",
        "libraries": (sysroot / "usr/lib/x86_64-linux-gnu", sysroot / "usr/lib"),
        "source": root / "src",
        "scorer_site": root / "runs/software-benchmark-v054/scorer-venv/lib/python3.12/site-packages",
        "shared_site": root / "runs/v016-sdk/resident-venv/lib/python3.12/site-packages",
    }


def validate_layout(paths):
    for name in ("loader", "python"):
        path = paths[name]
        if (not path.is_file() or not os.access(path, os.X_OK)
                or not path.resolve().is_relative_to(paths["sysroot"])):
            raise ValueError("Missing fixed private runtime executable: " + name)
    for path in (*paths["libraries"], paths["python_home"] / "lib/python3.12",
                 paths["source"], paths["scorer_site"], paths["shared_site"]):
        if not path.is_dir():
            raise ValueError("Missing fixed scorer runtime directory: " + str(path))
    bridge = paths["scorer_site"] / "resident-runtime.pth"
    if bridge.read_text().strip() != str(paths["shared_site"]):
        raise ValueError("Scorer package precedence differs from the frozen resident bridge")


def launch_spec(arguments, *, inherited=None, root=ROOT, sysroot=SYSROOT):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The scorer host launcher must run without root privileges")
    if not arguments:
        raise ValueError("Pass a Python script, -m MODULE, or -c CODE")
    paths = layout(root, sysroot)
    validate_layout(paths)
    parent = os.environ if inherited is None else inherited
    # Do not export the private libc path to child host tools such as git.
    # Site processing is disabled; the single existing .pth path is expanded
    # explicitly, preserving scorer-before-resident package precedence.
    env = {key: parent[key] for key in ("HOME", "USER", "LOGNAME", "TMPDIR") if key in parent}
    env.update(
        PATH="/usr/bin:/bin", LANG="C.UTF-8", LC_ALL="C.UTF-8",
        PYTHONHOME=str(paths["python_home"]),
        PYTHONPATH=os.pathsep.join(str(paths[key]) for key in ("source", "scorer_site", "shared_site")),
        PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONSAFEPATH="1",
        HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1", CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void",
        HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="", http_proxy="", https_proxy="", all_proxy="",
        NO_PROXY="*", no_proxy="*", PROWORKSIM_SCORER_HOST_LAUNCHER=VERSION,
    )
    command = [str(paths["loader"]), "--library-path",
               os.pathsep.join(map(str, paths["libraries"])), str(paths["python"]),
               "-B", "-S", "-P", *map(str, arguments)]
    return command, env


def main(arguments=None):
    command, env = launch_spec(sys.argv[1:] if arguments is None else arguments)
    os.chdir(ROOT)
    os.execve(command[0], command, env)


if __name__ == "__main__":
    main()

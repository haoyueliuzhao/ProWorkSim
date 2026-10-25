"""CPU-only command controls; no private interpreter, process, or socket starts."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("offline_scorer_launcher", ROOT / "tools/run_offline_scorer_v058.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def fixture(tmp_path, monkeypatch):
    root, sysroot = tmp_path / "project", tmp_path / "runtime"
    paths = launcher.layout(root, sysroot)
    for path in (*paths["libraries"], paths["python_home"] / "lib/python3.12",
                 paths["source"], paths["scorer_site"], paths["shared_site"]):
        path.mkdir(parents=True, exist_ok=True)
    for name in ("python", "loader"):
        path = paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic executable metadata only")
        path.chmod(0o700)
    (paths["scorer_site"] / "resident-runtime.pth").write_text(str(paths["shared_site"]) + "\n")
    monkeypatch.setattr(launcher.os, "getuid", lambda: 1001)
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 1001)
    return paths


def test_exact_python_uses_private_loader_without_inherited_runtime_or_proxy(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)
    args = ["-m", "proworksim.software_benchmark_scorer_v058", "--request", "request.json"]
    command, env = launcher.launch_spec(args, root=paths["root"], sysroot=paths["sysroot"],
        inherited={"HOME": "/synthetic/home", "PYTHONPATH": "/wrong", "LD_PRELOAD": "/wrong.so",
                   "LD_LIBRARY_PATH": "/wrong", "HTTPS_PROXY": "http://wrong", "DEEPSEEK_API_KEY": "do-not-inherit"})
    assert command == [str(paths["loader"]), "--library-path",
                       ":".join(map(str, paths["libraries"])), str(paths["python"]), "-B", "-S", "-P", *args]
    assert env["HOME"] == "/synthetic/home" and env["HTTPS_PROXY"] == ""
    assert env["PYTHONPATH"].split(":") == [str(paths[k]) for k in ("source", "scorer_site", "shared_site")]
    assert "LD_PRELOAD" not in env and "LD_LIBRARY_PATH" not in env and "DEEPSEEK_API_KEY" not in env


def test_refuses_root_and_changed_package_bridge(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 0)
    with pytest.raises(PermissionError, match="without root"):
        launcher.launch_spec(["-c", "pass"], root=paths["root"], sysroot=paths["sysroot"])
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 1001)
    (paths["scorer_site"] / "resident-runtime.pth").write_text("import arbitrary_module\n")
    with pytest.raises(ValueError, match="package precedence"):
        launcher.launch_spec(["-c", "pass"], root=paths["root"], sysroot=paths["sysroot"])


def test_main_only_execs_prepared_command_without_shell(monkeypatch):
    observed = []
    command, env = ["/fixed/loader", "--library-path", "/fixed/lib", "/fixed/python", "-c", "pass"], {"fixed": "env"}
    monkeypatch.setattr(launcher, "launch_spec", lambda args: (command, env))
    monkeypatch.setattr(launcher.os, "chdir", lambda path: observed.append(("cwd", path)))
    monkeypatch.setattr(launcher.os, "execve", lambda *args: observed.append(("exec", args)))
    launcher.main(["-c", "pass"])
    assert observed == [("cwd", launcher.ROOT), ("exec", (command[0], command, env))]

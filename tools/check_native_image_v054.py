"""One real shared-image CPU control: numeric ownership, public Python and resources."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import selectors
import subprocess
import traceback
import uuid

from proworksim.software_benchmark_native_rootfs_v054 import clone_prepared_rootfs, canonical
from proworksim.software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
from proworksim.software_benchmark_supervision_v054 import launch_owned, stop_owned

ROOT = Path(__file__).resolve().parents[1]


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def receive(process, timeout=60):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout):
            raise TimeoutError("Real-image worker RPC timed out")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Real-image worker closed without response")
        return json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--stdlib", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    public = json.loads(args.environment.read_bytes())
    source = Path(public["rootfs_manifest"])
    manifest = json.loads(source.read_bytes())
    result = {"version": "v054-native-real-image-control-v1", "passed": False,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "instance_id": manifest["instance_id"], "source_manifest": reference(source),
              "sources": [reference(ROOT / name) for name in (
                  "src/proworksim/software_benchmark_native_worker_v054.py",
                  "src/proworksim/software_benchmark_native_rootfs_v054.py",
                  "src/proworksim/software_benchmark_resources_v054.py",
                  "tools/native_uid_bootstrap_v054.py", "tools/run_native_worker_mapped_v054.sh")],
              "model_calls": 0, "gpu_launches": 0, "hidden_grader_called": False}
    process = scope = resources = None
    transcript = []
    try:
        clone = clone_prepared_rootfs(args.environment, out / "episode")
        resources = create_episode_resources(uuid.uuid4().hex, out)
        errors = (out / "worker.stderr").open("wb")
        process, scope = launch_owned([
            ROOT / "tools/run_native_worker_mapped_v054.sh", "--rootfs", clone["rootfs"],
            "--stdlib", args.stdlib.resolve(), "--environment-manifest", clone["environment_manifest"],
            "--preparation-only"], claim_id=resources["claim_id"], role="actor", runtime_seconds=180,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, resources=resources)
        ready = receive(process)
        transcript.append(ready)
        if ready["type"] != "ready":
            raise RuntimeError(str(ready))
        sequence = 0

        def call(tool, action):
            nonlocal sequence
            sequence += 1
            request = {"id": sequence, "tool": tool, "action": action}
            process.stdin.write((json.dumps(request) + "\n").encode())
            process.stdin.flush()
            response = receive(process)
            transcript.append({"request": request, "response": response})
            if response.get("type") != "observation" or response.get("id") != sequence:
                raise RuntimeError(str(response))
            return response["observation"]

        owners = {}
        for item in manifest["entries"]:
            owners.setdefault((item["uid"], item["gid"]), item["path"])
        cases = [["/" + path, uid, gid] for (uid, gid), path in owners.items()]
        probe = (
            "import os,json,socket,subprocess,sys\n"
            "import astropy\n"
            "assert astropy.__file__.startswith('/testbed/')\n"
            "assert sys.executable==" + repr(public["public_python"]) + "\n"
            "cases=" + repr(cases) + "\n"
            "for path,uid,gid in cases:\n"
            " s=os.lstat(path); assert (s.st_uid,s.st_gid)==(uid,gid),(path,s.st_uid,s.st_gid)\n"
            "head=subprocess.check_output(['git','-C','/testbed','rev-parse','HEAD','HEAD^{tree}'],text=True).splitlines()\n"
            "assert head==" + repr([manifest["actor_head"], manifest["actor_tree"]]) + "\n"
            "server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)\n"
            "client=socket.socket();client.settimeout(2);client.connect(server.getsockname())\n"
            "accepted,_=server.accept();client.sendall(b'ok');assert accepted.recv(2)==b'ok'\n"
            "accepted.close();client.close();server.close()\n"
            "print(json.dumps({'public_python':sys.executable,'public_module':astropy.__file__,'uid_cases':cases,'git':head,'loopback':True}))\n")
        observed = call("terminal", {"command": "python - <<'PWS_PUBLIC_CPU'\n" + probe + "PWS_PUBLIC_CPU",
                                     "timeout": 45})
        if observed["exit_code"] != 0:
            raise RuntimeError("Real public interpreter/UID/Git control failed: " + str(observed))
        denied = call("file_editor", {"command": "view", "path": str(ROOT / "src/proworksim/software_benchmark_native_worker_v054.py")})
        if denied["is_error"] is not True:
            raise RuntimeError("Host SDK control files visible in Actor root")
        process.stdin.write((json.dumps({"id": sequence + 1, "op": "close"}) + "\n").encode())
        process.stdin.flush()
        closed = receive(process)
        if closed.get("official_terminal_close_returned") is not True:
            raise RuntimeError("Official terminal did not close")
        if process.wait(timeout=30) != 0:
            raise RuntimeError("Mapped worker exited abnormally")
        quiet = stop_owned(scope)
        result.update(passed=True, ready=ready, scope=scope, quiescence=quiet,
                      resource_slice=resources, public_probe=observed, original_numeric_owner_pairs=len(owners),
                      host_control_files_denied=True, exit_code=0)
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    finally:
        if scope is not None:
            try:
                stop_owned(scope)
            except Exception as error:
                result["cleanup_error"] = repr(error)
                result["passed"] = False
        if process is not None and process.poll() is None:
            process.wait(timeout=30)
        if resources is not None:
            result["resource_release"] = release_episode_resources(resources)
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (out / "transcript.json").write_bytes(canonical(transcript))
        (out / "receipt.json").write_bytes(canonical(result))
    if result["passed"]:
        source.with_name("rootfs-manifest-before-native-control.json").write_bytes(source.read_bytes())
        args.environment.with_name("public-environment-before-native-control.json").write_bytes(args.environment.read_bytes())
        manifest.update(native_real_task_control_passed=True, native_control_receipt=reference(out / "receipt.json"))
        source.write_bytes(canonical(manifest))
        public["rootfs_manifest_sha256"] = reference(source)["sha256"]
        args.environment.write_bytes(canonical(public))
    print(json.dumps({key: result[key] for key in ("passed", "instance_id", "model_calls", "gpu_launches")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""One real zero-generation v055 actor/controller network and cgroup control."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def metadata_probe(key_file, output):
    from proworksim.software_benchmark_deepseek_api_v055 import DirectHTTPS, MODEL, load_api_key
    transport = DirectHTTPS(load_api_key(key_file), timeout_seconds=60)
    body = transport.request("GET", "/models")
    ids = [row["id"] for row in body["data"]]
    value = {"official_host": "api.deepseek.com", "port": 443, "path": "/models",
        "metadata_requests": 1, "generation_requests": 0, "observed_models": ids,
        "expected_alias_present": MODEL in ids, "reverse_proxy": False,
        "environment_proxy_used": False, "redirects_followed": False,
        "tls_certificate_verification": True, "actual_private_sdk_runtime": True}
    with output.open("x") as stream:
        json.dump(value, stream, indent=2)
    if MODEL not in ids:
        raise ValueError("Expected model alias absent from official private-runtime response")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", type=Path)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    if args.metadata_only:
        metadata_probe(args.key_file, args.output)
        return 0
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    from proworksim.software_benchmark_prewarm_v054 import qualified_paths
    from proworksim.software_benchmark_network_v055 import direct_environment_command, validate_actor_ready
    from proworksim.software_benchmark_rootfs_v055 import clone_prepared_rootfs
    from proworksim.software_benchmark_rootfs_io_v055 import cleanup_episode_rootfs
    from proworksim.software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
    from proworksim.software_benchmark_supervision_v054 import claim_nonce, launch_owned, stop_owned
    from proworksim.software_benchmark_runner_v054 import read_frame

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.source_config.read_bytes())
    result = {"version": "v055-real-network-resource-control-r1", "passed": False,
        "started_utc": datetime.now(timezone.utc).isoformat(), "generation_requests": 0,
        "formal_claims": 0, "GPU_loads": 0, "hidden_tests": 0,
        "source_config": reference(args.source_config)}
    scopes, processes, resources, clone = [], [], None, None
    try:
        prepared = qualified_paths(config["public_task"]["instance_id"],
            mapping_reference=config["scorer_request_base"]["baseline_mapping"],
            cache_root=Path(config["lazy_native_preparation"]["cache_root"]))
        clone = clone_prepared_rootfs(prepared["rootfs_environment"], out / "actor")
        resources = create_episode_resources(claim_nonce(), out)
        process, scope = launch_owned([ROOT / "tools/run_native_worker_mapped_v055.sh",
            "--rootfs", clone["rootfs"], "--stdlib", config["stdlib"],
            "--environment-manifest", clone["environment_manifest"]],
            claim_id=resources["claim_id"], role="actor", resources=resources,
            runtime_seconds=240, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=(out / "actor.stderr").open("xb"))
        processes.append(process)
        scopes.append(scope)
        ready = read_frame(process.stdout)
        write_new(out / "actor-ready.json", ready)
        result["network_boundary"] = validate_actor_ready(ready)
        probe = """import errno,json,os,socket,pathlib
assert not any('API_KEY' in name for name in os.environ)
assert not pathlib.Path('/data0/zhuxinrui/projects/ProWorkSim/.env').exists()
s=socket.socket();s.settimeout(2)
try:
 s.connect(('198.51.100.1',443))
except OSError as exc:
 assert exc.errno in (errno.ENETUNREACH,errno.EPERM,errno.EACCES),exc.errno
 print(json.dumps({'external_connect_denied':True,'errno':exc.errno,'actor_key_absent':True,'host_key_file_absent':True}))
else:
 raise RuntimeError('Actor unexpectedly reached an external route')
finally:
 s.close()
"""
        request = {"id": 1, "tool": "terminal", "action": {
            "command": "python - <<'V055_NETWORK_CONTROL'\n" + probe + "V055_NETWORK_CONTROL", "timeout": 20}}
        process.stdin.write((json.dumps(request) + "\n").encode())
        process.stdin.flush()
        observed = read_frame(process.stdout, timeout=30)
        write_new(out / "actor-probe.json", {"request": request, "response": observed})
        if observed.get("observation", {}).get("exit_code") != 0:
            raise RuntimeError("Real isolated Actor network/key control failed")
        process.stdin.write(b'{"id":2,"op":"close"}\n')
        process.stdin.flush()
        close = read_frame(process.stdout, timeout=20)
        if close.get("official_terminal_close_returned") is not True or process.wait(timeout=30) != 0:
            raise RuntimeError("Native Actor did not close")
        result["actor_quiescence"] = stop_owned(scope)
        command = direct_environment_command([
            ROOT / "tools/run_native_sdk_controller_v055.sh", config["sdk_runtime"], clone["rootfs"],
            Path(__file__).resolve(), "--metadata-only", "--key-file", args.key_file.resolve(),
            "--output", out / "private-controller-models.json"])
        controller, control_scope = launch_owned(command, claim_id=resources["claim_id"],
            role="controller", resources=resources, runtime_seconds=150,
            stdin=subprocess.DEVNULL, stdout=(out / "controller.stdout").open("xb"),
            stderr=(out / "controller.stderr").open("xb"))
        processes.append(controller)
        scopes.append(control_scope)
        if controller.wait(timeout=140) != 0:
            raise RuntimeError("Private SDK runtime direct metadata probe failed")
        result["controller_quiescence"] = stop_owned(control_scope)
        result.update(passed=True, resource_slice=resources,
                      metadata=reference(out / "private-controller-models.json"))
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        quiet = []
        for process, scope in reversed(list(zip(processes, scopes))):
            try:
                quiet.append(stop_owned(scope))
                process.wait(timeout=30)
            except Exception as error:
                result["passed"] = False
                result.setdefault("cleanup_errors", []).append(type(error).__name__)
        if resources is not None:
            result["resource_release"] = release_episode_resources(resources)
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        control = write_new(out / "receipt-before-cleanup.json", result)
        if clone is not None and quiet and not result.get("cleanup_errors"):
            proof = write_new(out / "quiescence.json", {"all_quiet": True, "stopped": quiet,
                                                       "outer_launcher_reaped": True})
            result["clone_cleanup"] = cleanup_episode_rootfs(clone["rootfs"], out,
                reference(clone["rootfs_manifest"]), proof, [control])
        write_new(out / "receipt.json", result)
    print(json.dumps({key: result[key] for key in ("passed", "generation_requests", "formal_claims", "GPU_loads")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

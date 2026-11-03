#!/usr/bin/env python3
"""CPU-only controls for the scoring-side SSL CA mapping; no sockets/processes."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import ssl
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/proworksim/software_benchmark_grading_ca_v114.py"


def run():
    forbidden = {"network": 0, "subprocess": 0}

    def audit(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
            forbidden["network"] += 1
            raise RuntimeError("No network is allowed in CA CPU controls")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            forbidden["subprocess"] += 1
            raise RuntimeError("No process launch is allowed in CA CPU controls")

    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location("scoring_ca_v114_cpu", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = module.profile_manifest()
    native_loader = ssl.SSLContext.load_verify_locations
    reports = []
    for task in module.TASKS:
        original = module._checked(profile["tasks"][task]["original_CA"])
        combined = module._checked(profile["tasks"][task]["combined_CA"])
        assert combined.startswith(original)
        with tempfile.TemporaryDirectory(prefix="pws-v114-ca-cpu-") as tmp:
            work = Path(tmp)
            original_file = work / "requests/cacert.pem"
            fixture = work / "ca-v114"
            original_file.parent.mkdir()
            fixture.mkdir()
            original_file.write_bytes(original)
            combined_file = fixture / "combined-ca.pem"
            combined_file.write_bytes(combined)
            other_file = work / "unrelated-ca.pem"
            other_file.write_bytes(original)
            original_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            native_loader(original_context, cafile=str(original_file))
            original_count = len(original_context.get_ca_certs())
            calls = []

            def observe(context, cafile=None, capath=None, cadata=None):
                calls.append({"cafile": cafile, "capath": capath, "cadata": cadata})
                return native_loader(context, cafile=cafile, capath=capath, cadata=cadata)

            ssl.SSLContext.load_verify_locations = observe
            source = module._shim_source(task, hashlib.sha256(original).hexdigest(), hashlib.sha256(combined).hexdigest(),
                                         original_path=str(original_file), fixture_root=str(fixture))
            namespace = {}
            try:
                exec(compile(source, "owned-cpu-sitecustomize.py", "exec"), namespace)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                before = (context.verify_mode, context.check_hostname)
                context.load_verify_locations(cafile=str(original_file))
                assert calls[-1]["cafile"] == str(combined_file)
                assert (context.verify_mode, context.check_hostname) == before == (ssl.CERT_REQUIRED, True)
                combined_count = len(context.get_ca_certs())
                assert combined_count > original_count
                other_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                other_context.load_verify_locations(cafile=other_file)
                assert calls[-1]["cafile"] is other_file
                assert len(other_context.get_ca_certs()) == original_count
                # Verify cadata/capath pass-through while the actual C loader runs.
                pem = re.search(br"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", original, re.S)[0].decode("ascii")
                der = ssl.PEM_cert_to_DER_cert(pem)
                context.load_verify_locations(cafile=bytes(str(original_file), "utf-8"), capath=str(work), cadata=der)
                assert calls[-1] == {"cafile": str(combined_file), "capath": str(work), "cadata": der}
                context.load_verify_locations(cadata=der)
                assert calls[-1] == {"cafile": None, "capath": None, "cadata": der}
                original_file.write_bytes(original + b"\n#changed\n")
                before_failure_calls = len(calls)
                try:
                    context.load_verify_locations(cafile=str(original_file))
                    raise AssertionError("Changed original CA accepted")
                except ssl.SSLError:
                    pass
                assert len(calls) == before_failure_calls
                original_file.write_bytes(original)
                combined_file.write_bytes(combined + b"\n#changed\n")
                try:
                    context.load_verify_locations(cafile=str(original_file))
                    raise AssertionError("Changed combined CA accepted")
                except ssl.SSLError:
                    pass
                assert len(calls) == before_failure_calls
                assert original_file.read_bytes() == original
            finally:
                ssl.SSLContext.load_verify_locations = native_loader
            archive = module._archive(task)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                assert sorted(tar.getnames()) == ["combined-ca.pem", "profile.json", "sitecustomize.py"]
                assert all(entry.mode == 0o444 and entry.isfile() and "/" not in entry.name for entry in tar.getmembers())
            reports.append({"instance_id": task, "passed": True, "real_native_SSL_loader_calls": len(calls),
                            "original_CA_count": original_count, "augmented_CA_count": combined_count,
                            "exact_original_path_mapped": True, "unrelated_cafile_unchanged": True,
                            "capath_and_cadata_unchanged": True, "verify_mode_and_hostname_checks_unchanged": True,
                            "changed_original_and_combined_files_fail_closed_before_native_loader": True,
                            "archive_contains_only_three_owned_regular_files": True})
    try:
        module.container_artifacts("psf__requests-2931")
        raise AssertionError("Unapproved task accepted")
    except ValueError:
        pass
    env = module.fixture_environment({"PYTHONPATH": "/existing/path", "UNCHANGED": "yes"})
    assert env == {"PYTHONPATH": module.FIXTURE_ROOT + ":/existing/path", "UNCHANGED": "yes"}
    assert ssl.SSLContext.load_verify_locations is native_loader
    result = {"version": "v114-scoring-CA-real-SSL-CPU-controls-r1", "status": "passed", "tasks": reports,
              "profile": module._reference(module.PROFILE_FILE), "adapter": module._reference(SOURCE),
              "effective_CA_changed": True, "original_CA_file_unchanged": True,
              "scope_rejects_other_tasks": True, "fixture_environment_preserves_other_values": True,
              "native_SSL_method_restored_after_CPU_controls": True,
              "forbidden_operation_counts": forbidden, "Docker_operations": 0, "model_calls": 0,
              "host_configuration_modified": False, "container_interpreter_and_real_TLS_not_yet_validated": True,
              "fresh_gold_empty_controls_remain_required": True}
    output = ROOT / "artifacts/software-benchmark-v114/grading-ca-controls-r1/summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
"""Run with python3 -S -B: real old Requests CA selection and SSL, no network.

The actual original package is copied to temporary source/installed layouts.
Only the final SSLContext.wrap_socket is scripted. load_verify_locations reaches
the actual native SSL loader. -S omits optional host OpenSSL dependencies; local
collections aliases accommodate the newer CPU interpreter without editing the
old package. This does not claim container/interpreter or live-TLS equivalence.
"""
import collections
import collections.abc
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import tempfile
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/proworksim/software_benchmark_grading_ca_v116.py"


def run():
    if not sys.flags.no_site:
        raise RuntimeError("Use python3 -S -B to avoid optional host OpenSSL injection")
    forbidden = {"network": 0, "subprocess": 0}

    def audit(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
            forbidden["network"] += 1
            raise RuntimeError("CA CPU controls cannot open network connections")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            forbidden["subprocess"] += 1
            raise RuntimeError("CA CPU controls cannot launch subprocesses")

    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location("scoring_ca_v116_cpu", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = module.profile_manifest()
    native_loader = ssl.SSLContext.load_verify_locations
    native_wrap = ssl.SSLContext.wrap_socket
    initial_path = list(sys.path)
    aliases = []
    for name in ("Mapping", "MutableMapping", "Callable"):
        if not hasattr(collections, name):
            setattr(collections, name, getattr(collections.abc, name))
            aliases.append(name)
    reports = []
    for task in module.TASKS:
        entry = profile["tasks"][task]
        frozen = json.loads(module._checked(entry["original_snapshot"]))["files"]
        original = module._checked(entry["original_CA"])
        combined = module._checked(entry["combined_CA"])
        with tempfile.TemporaryDirectory(prefix="pws-v116-requests-ca-") as temporary:
            workspace = Path(temporary)
            source_root = workspace / "testbed"
            installed_root = workspace / "opt/miniconda3/envs/testbed/lib/python3.9/site-packages"
            fixture = workspace / "pws-fixtures/ca-v116"
            fixture.mkdir(parents=True)
            combined_file = fixture / "combined-ca.pem"
            combined_file.write_bytes(combined)
            for package_root in (source_root, installed_root):
                for filename, content in frozen.items():
                    if filename.startswith("requests/") and (filename.endswith(".py") or filename == "requests/cacert.pem"):
                        relative = Path(filename)
                        if relative.is_absolute() or ".." in relative.parts:
                            raise ValueError("Nonlocal original package path")
                        destination = package_root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(content)
            allowed_paths = (str(source_root / "requests/cacert.pem"), str(installed_root / "requests/cacert.pem"))
            assert all(Path(p).read_bytes() == original for p in allowed_paths)
            shim = module._shim_source(task, entry["original_CA_sha256"], entry["combined_CA"]["sha256"],
                                       allowed_paths=allowed_paths, fixture_root=str(fixture))
            for layout, package_root in (("source", source_root), ("installed", installed_root)):
                for name in list(sys.modules):
                    if name == "requests" or name.startswith("requests."):
                        del sys.modules[name]
                sys.path[:] = [str(package_root), *initial_path]
                importlib.invalidate_caches()
                requests = importlib.import_module("requests")
                adapters = importlib.import_module("requests.adapters")
                util = importlib.import_module("requests.packages.urllib3.util")
                selected_ca = requests.certs.where()
                assert selected_ca == str(package_root / "requests/cacert.pem")
                assert util.SSLContext is ssl.SSLContext
                connection = SimpleNamespace()
                adapters.HTTPAdapter().cert_verify(connection, "hTtPs://httpbin.org/get", True, None)
                assert connection.ca_certs == selected_ca and connection.cert_reqs == "CERT_REQUIRED"
                calls, wrapped = [], []

                def observe(context, cafile=None, capath=None, cadata=None):
                    before = (context.verify_mode, context.check_hostname)
                    result = native_loader(context, cafile=cafile, capath=capath, cadata=cadata)
                    assert (context.verify_mode, context.check_hostname) == before
                    calls.append({"cafile": cafile, "capath": capath, "cadata": cadata,
                                  "native_loader_completed": True, "security_before_after_same": True})
                    return result

                def finish_socket(context, socket, **kwargs):
                    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
                    assert kwargs.get("server_hostname") == "httpbin.org"
                    value = {"CA_count": len(context.get_ca_certs()), "verify_mode": int(context.verify_mode),
                             "check_hostname": context.check_hostname, "server_hostname": kwargs["server_hostname"]}
                    wrapped.append(value)
                    return value

                ssl.SSLContext.load_verify_locations = observe
                ssl.SSLContext.wrap_socket = finish_socket
                try:
                    exec(compile(shim, "owned-v116-sitecustomize.py", "exec"), {})
                    # Execute the actual original urllib3 TLS helper, including
                    # its SSLContext construction and load_verify_locations.
                    value = util.ssl_wrap_socket(object(), cert_reqs=getattr(ssl, connection.cert_reqs),
                                                 ca_certs=connection.ca_certs, server_hostname="httpbin.org",
                                                 ssl_version=ssl.PROTOCOL_TLS_CLIENT)
                    assert len(calls) == 1 and calls[0]["cafile"] == str(combined_file)
                    assert value == wrapped[0]
                    other = workspace / "unrelated-ca.pem"
                    other.write_bytes(original)
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.load_verify_locations(cafile=other, capath=str(workspace))
                    assert calls[-1]["cafile"] is other and calls[-1]["capath"] == str(workspace) and calls[-1]["cadata"] is None
                    # Both allowlisted copies must keep the same original hash,
                    # including the copy not selected by this package layout.
                    other_allowed = Path(allowed_paths[1 if layout == "source" else 0])
                    other_allowed.write_bytes(original + b"\n# changed CPU fixture\n")
                    before_calls = len(calls)
                    try:
                        context.load_verify_locations(cafile=selected_ca)
                        raise AssertionError("Mismatched alternative original CA accepted")
                    except ssl.SSLError:
                        pass
                    assert len(calls) == before_calls
                    other_allowed.write_bytes(original)
                    assert all(Path(p).read_bytes() == original for p in allowed_paths)
                finally:
                    ssl.SSLContext.load_verify_locations = native_loader
                    ssl.SSLContext.wrap_socket = native_wrap
                reports.append({"instance_id": task, "layout": layout, "requests_version": requests.__version__,
                                "actual_certs_where_selected_layout": True, "actual_HTTPAdapter_cert_verify_used": True,
                                "actual_original_urllib3_ssl_wrap_socket_used": True, "native_SSL_loader_completed": True,
                                "original_certs_py_sha256": hashlib.sha256(frozen["requests/certs.py"].encode()).hexdigest(),
                                "original_adapters_py_sha256": hashlib.sha256(frozen["requests/adapters.py"].encode()).hexdigest(),
                                "only_final_wrap_socket_scripted": True, "loader_attributes_fabricated": False,
                                "unrelated_cafile_and_capath_passthrough": True, "both_original_CA_hashes_required": True,
                                "security": value, "original_CA_files_unchanged_after_control": True})
    sys.path[:] = initial_path
    for name in list(sys.modules):
        if name == "requests" or name.startswith("requests."):
            del sys.modules[name]
    for name in aliases:
        delattr(collections, name)
    assert ssl.SSLContext.load_verify_locations is native_loader and ssl.SSLContext.wrap_socket is native_wrap
    result = {"version": "v116-original-Requests-source-installed-native-SSL-controls-r1", "status": "passed",
              "profile": module._reference(module.PROFILE_FILE), "adapter": module._reference(SOURCE), "cases": reports,
              "effective_CA_changed": True, "CA_bundle_bytes_changed_from_v114": False,
              "CPU_only_compatibility_aliases": aliases, "optional_host_site_packages_excluded_with_dash_S": True,
              "forbidden_operation_counts": forbidden, "Docker_operations": 0, "API_calls": 0,
              "host_configuration_modified": False, "live_TLS_and_container_interpreter_not_claimed": True}
    output = ROOT / "artifacts/software-benchmark-v116/grading-ca-controls-r1/summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()

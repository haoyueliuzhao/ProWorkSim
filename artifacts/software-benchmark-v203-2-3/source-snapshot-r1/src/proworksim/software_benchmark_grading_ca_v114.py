"""Explicit scoring-only CA augmentation for the two old Requests clients.

This changes effective trust anchors, not the repository CA file, prediction,
certificate verification requirement, or hostname verification. Preparation is
CPU/file-only; bind_tls itself creates no containers or network connections.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v114-scoring-only-original-plus-current-ca-r1"
TASKS = ("psf__requests-1766", "psf__requests-1921")
ORIGINAL_CA = "/testbed/requests/cacert.pem"
FIXTURE_ROOT = "/pws-fixtures/ca-v114"
ASSETS = ROOT / "artifacts/software-benchmark-v114/grading-ca-profile-r1"
PROFILE_FILE = ROOT / "runs/software-benchmark-v111/aligned-interface-r1/recovery-v114/ca-profile.json"
ORIGINAL_SOURCES = {
    "psf__requests-1766": (7066, "113be89390a3358988484f3e9fa903751abc168f3f4ba9e2ee899fc1b15b8216"),
    "psf__requests-1921": (7038, "6a4eeafeaf28cc7750f5f7f6ed4f84d6f08dacb8ac151412332f732647694253"),
}


def _digest(body):
    return hashlib.sha256(body).hexdigest()


def _reference(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {"path": str(path), "sha256": _digest(body), "bytes": len(body)}


def _checked(ref):
    body = Path(ref["path"]).read_bytes()
    if _digest(body) != ref["sha256"] or len(body) != ref["bytes"]:
        raise ValueError("Frozen public CA artifact identity changed")
    return body


def _retain(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError("Refuse to replace a frozen CA preparation artifact")
    else:
        path.write_bytes(body)
    return _reference(path)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _shim_source(task, original_sha256, bundle_sha256, *, original_path=ORIGINAL_CA, fixture_root=FIXTURE_ROOT):
    """Generated standalone Python 3 shim; test paths are isolated CPU fixtures."""
    bundle_path = fixture_root + "/combined-ca.pem"
    return ('''# Frozen scoring fixture. Effective CA trust changes; repository bytes do not.
import hashlib as _hashlib
import os as _os
import ssl as _ssl

PWS_CA_VERSION = %r
PWS_CA_TASK = %r
PWS_CA_ORIGINAL_PATH = %r
PWS_CA_ORIGINAL_SHA256 = %r
PWS_CA_COMBINED_PATH = %r
PWS_CA_COMBINED_SHA256 = %r
_original_loader = _ssl.SSLContext.load_verify_locations

def _sha(path):
    with open(path, 'rb') as stream:
        return _hashlib.sha256(stream.read()).hexdigest()

def _load_verify_locations(self, cafile=None, capath=None, cadata=None):
    selected = cafile
    if cafile is not None:
        try:
            normalized = _os.path.abspath(_os.fsdecode(_os.fspath(cafile)))
        except (TypeError, ValueError):
            normalized = None
        if normalized == PWS_CA_ORIGINAL_PATH:
            if _sha(PWS_CA_ORIGINAL_PATH) != PWS_CA_ORIGINAL_SHA256:
                raise _ssl.SSLError('The original scoring CA file changed; trust augmentation refused')
            if _sha(PWS_CA_COMBINED_PATH) != PWS_CA_COMBINED_SHA256:
                raise _ssl.SSLError('The frozen scoring CA bundle changed; trust augmentation refused')
            selected = PWS_CA_COMBINED_PATH
    # capath/cadata and context security settings are never rewritten.
    return _original_loader(self, cafile=selected, capath=capath, cadata=cadata)

_load_verify_locations._pws_scoring_ca_version = PWS_CA_VERSION
_load_verify_locations._pws_scoring_ca_task = PWS_CA_TASK
_load_verify_locations._pws_scoring_ca_bundle_sha256 = PWS_CA_COMBINED_SHA256
if getattr(_original_loader, '_pws_scoring_ca_version', None) is not None:
    raise RuntimeError('A second scoring CA wrapper is not allowed')
_ssl.SSLContext.load_verify_locations = _load_verify_locations
''' % (VERSION, task, original_path, original_sha256, bundle_path, bundle_sha256)).encode()


def prepare_profile(*, system_ca=Path("/etc/ssl/certs/ca-certificates.crt"), profile_file=PROFILE_FILE):
    """Freeze public certificate bytes, with no service, Docker, or network call."""
    system_ca = Path(system_ca).resolve()
    public = system_ca.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" not in public or b"PRIVATE KEY" in public:
        raise ValueError("Expected a public CA certificate bundle only")
    current_ref = _retain(ASSETS / "system-public-ca.pem", public)
    profiles = {}
    for task, (slot, expected) in ORIGINAL_SOURCES.items():
        source = ROOT / f"runs/software-benchmark-v105/nonthinking-interface-r1/episodes/{slot}/baseline-snapshot.json"
        original = json.loads(source.read_bytes())["files"]["requests/cacert.pem"].encode("utf-8")
        if _digest(original) != expected or b"PRIVATE KEY" in original:
            raise ValueError("The recorded original public CA identity differs")
        # Preserve the original bytes as an exact prefix; separator is appended.
        combined = original + b"\n" + public
        original_ref = _retain(ASSETS / f"{task}-original-ca.pem", original)
        combined_ref = _retain(ASSETS / f"{task}-combined-ca.pem", combined)
        shim = _shim_source(task, expected, combined_ref["sha256"])
        shim_ref = _retain(ASSETS / f"{task}-sitecustomize.py", shim)
        profiles[task] = {"instance_id": task, "original_CA_path": ORIGINAL_CA,
                          "original_CA_sha256": expected, "original_snapshot": _reference(source),
                          "original_CA": original_ref, "combined_CA": combined_ref, "sitecustomize": shim_ref,
                          "container_fixture_root": FIXTURE_ROOT, "original_bytes_are_exact_combined_prefix": True}
    manifest = {"version": VERSION, "tasks": profiles, "system_public_CA": current_ref,
                "system_CA_source": _reference(system_ca), "effective_CA_changed": True,
                "original_CA_file_unchanged": True, "prediction_patch_bytes_unchanged": True,
                "certificate_verification_required": True, "hostname_verification_unchanged": True,
                "verify_mode_modified": False, "check_hostname_modified": False,
                "scope": "Only newly authorized scoring containers for Requests 1766/1921; never actor/model workspaces or host configuration",
                "user_authorization": "User explicitly allowed scoring-side CA updates; this profile does not itself authorize any Docker or network operation",
                "fresh_gold_empty_controls_required": True, "historical_original_CA_scores_rewritten": False}
    return _retain(profile_file, _json_bytes(manifest))


def profile_manifest():
    value = json.loads(PROFILE_FILE.read_bytes())
    if value.get("version") != VERSION or set(value.get("tasks", {})) != set(TASKS):
        raise ValueError("A frozen scoring-only two-task CA profile is required")
    current = _checked(value["system_public_CA"])
    for task in TASKS:
        entry = value["tasks"][task]
        original, combined = _checked(entry["original_CA"]), _checked(entry["combined_CA"])
        if (entry["original_CA_sha256"] != ORIGINAL_SOURCES[task][1]
                or _digest(original) != entry["original_CA_sha256"]
                or entry["original_CA_path"] != ORIGINAL_CA
                or combined != original + b"\n" + current
                or _checked(entry["sitecustomize"]) != _shim_source(task, entry["original_CA_sha256"], _digest(combined))):
            raise ValueError("CA concatenation or exact loader shim differs from the frozen profile")
    return value


def container_artifacts(task):
    if task not in TASKS:
        raise ValueError("CA compatibility is limited to Requests 1766/1921 scoring")
    manifest = profile_manifest()
    entry = manifest["tasks"][task]
    return {"sitecustomize.py": _checked(entry["sitecustomize"]),
            "combined-ca.pem": _checked(entry["combined_CA"]),
            "profile.json": _json_bytes({"version": VERSION, "instance_id": task,
                "effective_CA_changed": True, "original_CA_file_unchanged": True,
                "original_CA_path": ORIGINAL_CA, "original_CA_sha256": entry["original_CA_sha256"],
                "combined_CA_sha256": entry["combined_CA"]["sha256"]})}


def _archive(task):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, body in container_artifacts(task).items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.uid, info.gid, info.mtime = len(body), 0o444, 0, 0, 0
            archive.addfile(info, io.BytesIO(body))
    return output.getvalue()


def fixture_environment(values):
    if isinstance(values, list):
        values = dict(item.split("=", 1) for item in values)
    result = dict(values or {})
    paths = [p for p in result.get("PYTHONPATH", "").split(":") if p and p != FIXTURE_ROOT]
    result["PYTHONPATH"] = ":".join([FIXTURE_ROOT, *paths])
    return result


def _probe_source(task):
    entry = profile_manifest()["tasks"][task]
    return "\n".join([
        "import hashlib,json,ssl,sitecustomize",
        "expected_task=" + repr(task),
        "expected_bundle=" + repr(entry["combined_CA"]["sha256"]),
        "loader=ssl.SSLContext.load_verify_locations",
        "assert getattr(loader,'_pws_scoring_ca_task',None)==expected_task",
        "assert getattr(loader,'_pws_scoring_ca_bundle_sha256',None)==expected_bundle",
        "context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)",
        "before=(context.verify_mode,context.check_hostname)",
        "context.load_verify_locations(cafile=" + repr(ORIGINAL_CA) + ")",
        "after=(context.verify_mode,context.check_hostname)",
        "assert before==after and context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname",
        "print(json.dumps({'effective_CA_changed':True,'original_CA_file_unchanged':True,'verify_mode':int(context.verify_mode),'check_hostname':context.check_hostname,'loaded_CA_count':len(context.get_ca_certs()),'actual_SSL_loader_probe':True,'network_calls':0}))",
    ])


def bind_tls(tls):
    """Bind the caller's private scoring provider; no process-global mutation."""
    if set(tls.PROFILES) != set(TASKS):
        raise ValueError("Bind only the isolated two-task TLS scoring provider")
    if getattr(tls, "_v114_scoring_ca_bound", False):
        return tls
    # The existing builder must supply private function globals, not the shared
    # importable original module. Refuse a shared module instead of patching it.
    import sys
    if sys.modules.get(getattr(tls, "__name__", "")) is tls:
        raise ValueError("A private scoring provider namespace is required")
    original_manifest = tls.environment_manifest
    original_fixture = tls.fixture_environment
    parent = tls.EnvironmentContainer

    def manifest():
        base = original_manifest()
        return {**base, "version": VERSION, "scoring_CA_profile": _reference(PROFILE_FILE),
                "scoring_CA_compatibility": profile_manifest(), "effective_CA_changed": True,
                "original_CA_file_unchanged": True, "original_ca_changed": False,
                "tls_verification_changed": True,
                "tls_verification_change_scope": "Effective trusted CA set only; verification and hostname checks remain enabled",
                "certificate_verification_required": True, "hostname_verification_unchanged": True}

    def environment(values):
        return fixture_environment(original_fixture(values))

    class ScoringCAContainer(parent):
        def start(self, *args, **kwargs):
            task = self.preparation["mapping"]["instance_id"]
            if task not in TASKS:
                raise ValueError("The CA fixture cannot enter another task or actor")
            result = super().start(*args, **kwargs)
            expected = profile_manifest()["tasks"][task]
            if self.ca_before.get("sha256") != expected["original_CA_sha256"]:
                raise ValueError("The admitted repository CA differs from its task profile")
            actual_env = dict(item.split("=", 1) for item in self.delegate.attrs.get("Config", {}).get("Env", []) if "=" in item)
            if actual_env.get("PYTHONPATH", "").split(":")[0] != FIXTURE_ROOT:
                raise ValueError("The actual scoring interpreter lacks the frozen CA fixture path")
            tls.prior.checked_exec(self.delegate, ["mkdir", "-p", FIXTURE_ROOT], timeout_note="Owned scoring-only CA fixture directory")
            if self.delegate.put_archive(FIXTURE_ROOT, _archive(task)) is not True:
                raise RuntimeError("Scoring CA artifact upload was not acknowledged")
            probe = json.loads(tls.prior.checked_exec(self.delegate, [tls.PYTHON, "-B", "-c", _probe_source(task)], timeout_note="Scoring CA real SSL loader probe"))
            if tls.ca_identity(self.delegate) != self.ca_before:
                raise ValueError("Scoring CA preparation altered the original repository CA")
            evidence_path = Path(self.preparation["path"])
            evidence = json.loads(evidence_path.read_bytes())
            evidence.update(effective_CA_changed=True, original_CA_file_unchanged=True,
                            scoring_CA_profile=_reference(PROFILE_FILE), scoring_CA_loader_probe=probe,
                            original_ca_changed=False, tls_verification_changed=True,
                            tls_verification_change_scope="Effective trusted CA set only; certificate and hostname verification preserved")
            evidence_path.write_bytes(tls.base.canonical(evidence))
            return result

    tls.environment_manifest = manifest
    tls.fixture_environment = environment
    tls.EnvironmentContainer = ScoringCAContainer
    tls.validate_environment.__globals__["environment_manifest"] = manifest
    parent.start.__globals__["validate_environment"] = tls.validate_environment
    tls._v114_scoring_ca_bound = True
    return tls

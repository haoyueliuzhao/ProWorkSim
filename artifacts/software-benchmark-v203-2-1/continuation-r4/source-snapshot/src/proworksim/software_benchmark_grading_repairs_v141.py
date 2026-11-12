"""Offline build dependency plans and conservative TCP close evidence.

No operation here starts containers, installs host packages or contacts a
network. New grading environments still require actual gold/empty controls.
"""
from __future__ import annotations

from email.parser import BytesParser
import hashlib
import inspect
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tomllib
from types import ModuleType
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from . import software_benchmark_tcp_transport_v066 as original_tcp
from . import software_benchmark_io_v088 as io_adapter
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = "v141-offline-build-and-observed-tcp-closure-r1"
PYTEST_TASK = "pytest-dev__pytest-10081"
WHEELHOUSE = "/pws-v141-build-wheels"
PIP_ENVIRONMENT = {"PIP_NO_INDEX": "1", "PIP_FIND_LINKS": "file://"+WHEELHOUSE,
                   "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1",
                   "PIP_CONFIG_FILE": "/dev/null", "PIP_RETRIES": "0"}
ALLOWED_BUILD_EXTRAS = {"setuptools-scm": frozenset({"toml"})}


def inspect_wheel(ref, *, target_python):
    """Read frozen pure-Python wheel metadata; no importing or installing it."""
    path = checked(ref)
    if path.suffix != ".whl" or path.stat().st_size > 32*1024**2:
        raise ValueError("A bounded frozen wheel is required")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [row.filename for row in infos]
        if (len(names) != len(set(names)) or sum(row.file_size for row in infos) > 128*1024**2
                or any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names)
                or archive.testzip() is not None):
            raise ValueError("Wheel paths, size or CRC are invalid")
        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError("Exactly one wheel distribution metadata record is required")
        prefix = metadata_paths[0].rsplit("/", 1)[0]
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
        wheel = BytesParser().parsebytes(archive.read(prefix+"/WHEEL"))
        tags = set(wheel.get_all("Tag", []))
        if (wheel.get("Root-Is-Purelib") != "true" or not tags
                or not tags <= {"py3-none-any", "py2-none-any"}):
            raise ValueError("Only checked pure-Python wheel tags are admitted by this repair")
        python_spec = metadata.get("Requires-Python", "")
        if python_spec and Version(target_python) not in SpecifierSet(python_spec):
            raise ValueError("Wheel does not support the grading interpreter")
        name, version = metadata.get("Name"), metadata.get("Version")
        if not name or not version:
            raise ValueError("Distribution name/version missing")
        filename_name, filename_version, _, _ = parse_wheel_filename(path.name)
        if filename_name != canonicalize_name(name) or filename_version != Version(version):
            raise ValueError("Wheel filename and selected distribution metadata differ")
        requires = metadata.get_all("Requires-Dist", [])
        for requirement in requires:
            if Requirement(requirement).url:
                raise ValueError("Direct URL dependencies are forbidden in the offline plan")
    return {"wheel": ref, "name": canonicalize_name(name), "version": version,
            "requires_python": python_spec, "requires_dist": requires,
            "provides_extra": sorted(canonicalize_name(value) for value in metadata.get_all("Provides-Extra", [])),
            "destination": WHEELHOUSE+"/"+path.name}


def offline_build_plan(pyproject_ref, wheel_refs, *, target_python="3.9.20",
                       additional_build_requires=()):
    """Freeze the actual baseline build-system requirements and local closure.

    Dynamic backend requirements must be supplied from separately recorded
    container preflight. An empty list never claims they do not exist.
    """
    source = tomllib.loads(checked(pyproject_ref).read_text())
    build = source.get("build-system")
    if not isinstance(build, dict) or not isinstance(build.get("requires"), list) or not build["requires"]:
        raise ValueError("The actual baseline build-system requirements are required")
    wheels = [inspect_wheel(ref, target_python=target_python) for ref in wheel_refs]
    by_name = {row["name"]: row for row in wheels}
    if len(by_name) != len(wheels) or not wheels:
        raise ValueError("Use exactly one frozen version for each supplied build distribution")
    environment = default_environment()
    environment.update(python_version=".".join(target_python.split(".")[:2]),
                       python_full_version=target_python, implementation_name="cpython",
                       platform_python_implementation="CPython", sys_platform="linux", extra="")
    pending = [(value, frozenset()) for value in [*build["requires"], *additional_build_requires]]
    visited, edges = {}, []
    while pending:
        text, parent_extras = pending.pop()
        requirement = Requirement(text)
        if requirement.url:
            raise ValueError("URL dependencies require a separately reviewed explicit plan")
        if requirement.marker and not any(requirement.marker.evaluate({**environment, "extra": extra})
                                          for extra in ("", *sorted(parent_extras))):
            continue
        name = canonicalize_name(requirement.name)
        selected = by_name.get(name)
        if selected is None or Version(selected["version"]) not in requirement.specifier:
            raise ValueError("Missing or incompatible offline build dependency: "+text)
        extras = frozenset(canonicalize_name(extra) for extra in requirement.extras)
        if (not extras <= ALLOWED_BUILD_EXTRAS.get(name, frozenset())
                or not extras <= set(selected["provides_extra"])):
            raise ValueError("Requested build extras are not explicitly frozen and supported: "+text)
        edge = {"requirement": text, "selected_name": name, "selected_version": selected["version"],
                "selected_extras": sorted(extras)}
        if edge not in edges:
            edges.append(edge)
        previous = visited.get(name)
        active = extras | (previous or frozenset())
        if previous is None or active != previous:
            visited[name] = active
            pending.extend((value, active) for value in selected["requires_dist"])
    return {"version": VERSION, "instance_id": PYTEST_TASK, "baseline_pyproject": pyproject_ref,
            "target_python": target_python, "build_backend": build.get("build-backend"),
            "original_build_requires": list(build["requires"]),
            "additional_build_requires": list(additional_build_requires),
            "allowed_build_extras": {name: sorted(extras) for name, extras in ALLOWED_BUILD_EXTRAS.items()},
            "wheels": wheels, "requirement_resolution": sorted(edges, key=lambda row: row["requirement"]),
            "container_environment": dict(PIP_ENVIRONMENT), "network_mode": "none",
            "official_pip_command_changed": False, "build_isolation_disabled": False,
            "host_installation": False, "automatic_download": False,
            "dynamic_backend_requirements_verified": False, "runtime_qualified": False,
            "fresh_gold_empty_controls_required": True,
            "candidate_import_compatibility_unresolved": True}


def validate_offline_plan(ref):
    planned = json.loads(checked(ref).read_bytes())
    current = offline_build_plan(planned["baseline_pyproject"], [row["wheel"] for row in planned["wheels"]],
        target_python=planned["target_python"], additional_build_requires=planned["additional_build_requires"])
    if current != planned:
        raise ValueError("Frozen offline build dependency plan changed")
    return planned


def offline_environment(values):
    actual = dict(item.split("=", 1) for item in values) if isinstance(values, list) else dict(values or {})
    if any(key in actual and actual[key] != value for key, value in PIP_ENVIRONMENT.items()):
        raise ValueError("Conflicting pip network or dependency environment")
    for key in ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST", "PIP_NO_BUILD_ISOLATION"):
        actual.pop(key, None)
    return {**actual, **PIP_ENVIRONMENT}


def owned_wheel_archive(plan_ref, *, instance_id, container_id, owned_container_ids):
    """Bytes for a caller-authorized owned container; performs no transfer."""
    plan = validate_offline_plan(plan_ref)
    if instance_id != PYTEST_TASK or container_id not in owned_container_ids:
        raise ValueError("Offline build wheels belong only to the exact owned pytest scorer")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for row in plan["wheels"]:
            source = checked(row["wheel"])
            body = source.read_bytes()
            info = tarfile.TarInfo(source.name)
            info.size, info.mode, info.uid, info.gid, info.mtime = len(body), 0o444, 0, 0, 0
            archive.addfile(info, io.BytesIO(body))
    return {"destination": WHEELHOUSE, "archive": stream.getvalue(), "plan": plan_ref,
            "container_id": container_id, "network_calls": 0}


def bind_offline_build_scorer(scorer, plan_ref):
    """Wire the plan into actual newly owned scorer creation/start, no IO here."""
    plan = validate_offline_plan(plan_ref)
    namespace = scorer.score_request.__globals__
    original_container = namespace["ObservedContainer"]
    original_create = namespace["Containers"].create

    class ObservedContainer(original_container):
        def start(self, *args, **kwargs):
            result = super().start(*args, **kwargs)
            if self.preparation["mapping"]["instance_id"] != PYTEST_TASK:
                return result
            package = owned_wheel_archive(plan_ref, instance_id=PYTEST_TASK,
                container_id=self.delegate.id, owned_container_ids=self.v141_tracking["owned_container_ids"])
            self.delegate.reload()
            actual = dict(row.split("=", 1) for row in self.delegate.attrs["Config"].get("Env", []) if "=" in row)
            if any(actual.get(key) != value for key, value in PIP_ENVIRONMENT.items()):
                raise ValueError("The actual scoring process lacks the frozen offline pip environment")
            source = ("import hashlib,json,sys; print(json.dumps({'python':'.'.join(map(str,sys.version_info[:3])),"
                "'pyproject_sha256':hashlib.sha256(open('/testbed/pyproject.toml','rb').read()).hexdigest()}))")
            checked_exec = namespace["archive"].checked_exec
            python = self.preparation["mapping"]["public_python"]
            observed = json.loads(checked_exec(self.delegate, [python, "-B", "-c", source],
                timeout_note="Exact offline build baseline and interpreter"))
            if (observed["python"] != plan["target_python"]
                    or observed["pyproject_sha256"] != plan["baseline_pyproject"]["sha256"]):
                raise ValueError("The actual build baseline or interpreter differs from the frozen plan")
            checked_exec(self.delegate, ["mkdir", "-p", WHEELHOUSE], timeout_note="Owned offline build wheel directory")
            if self.delegate.put_archive(WHEELHOUSE, package["archive"]) is not True:
                raise ValueError("Owned scoring container rejected offline build wheel bytes")
            expected = {row["destination"]: row["wheel"]["sha256"] for row in plan["wheels"]}
            probe = "import hashlib,json; paths="+repr(expected)+"; print(json.dumps({p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}))"
            actual_hashes = json.loads(checked_exec(self.delegate, [python, "-B", "-c", probe],
                timeout_note="Uploaded frozen build wheel hashes"))
            if actual_hashes != expected:
                raise ValueError("Actual container build wheel hashes changed")
            write_new(Path(self.preparation["path"]).with_name("offline-build-preflight-v141.json"),
                {"version": VERSION, "plan": plan_ref, "instance_id": PYTEST_TASK,
                 "container_id": self.delegate.id, "actual_environment": dict(PIP_ENVIRONMENT),
                 "actual_baseline": observed, "actual_wheel_sha256": actual_hashes,
                 "official_command_changed": False, "network_calls": 0,
                 "actual_build_and_gold_empty_qualification_pending": True})
            return result

    create = clone_function(original_create,
        {**original_create.__globals__, **namespace, "ObservedContainer": ObservedContainer})

    class Containers(namespace["Containers"]):
        def create(self, **options):
            if self.observation["mapping"]["instance_id"] == PYTEST_TASK:
                options["environment"] = offline_environment(options.get("environment"))
            result = create(self, **options)
            result.v141_tracking = self.tracking
            return result

    namespace.update(ObservedContainer=ObservedContainer, Containers=Containers)
    scorer.ObservedContainer, scorer.Containers = ObservedContainer, Containers
    inherited_manifest = scorer.installation_manifest

    def installation_manifest():
        return {**inherited_manifest(), "offline_build_adapter": reference(__file__),
                "offline_build_plan": plan_ref, "official_pip_command_changed": False,
                "runtime_qualified_by_CPU_controls": False}

    namespace["installation_manifest"] = scorer.installation_manifest = installation_manifest
    return scorer


def transport_adapter(policy):
    """Rebind the existing relay to a new guard and retain actual EOF evidence.

    A clean already-observed two-sided EOF is finalized before idle accounting.
    Mere request/response bytes and an idle socket never establish success. The
    historical 1766 idle record lacks EOF flags and cannot be upgraded by this.
    """
    namespace = clone_namespace(original_tcp, select=io_adapter.POLL_SELECT, VERSION=VERSION)
    namespace["_authorize"] = lambda task: policy.require_v066_allowed("v066.transport", instance_id=task)
    source = inspect.getsource(original_tcp.relay_many)
    old_record = 'item.record["queued_client_bytes_discarded"] = len(item.outgoing)'
    new_record = old_record+'''\n        item.record.update(client_eof_observed=item.client_eof,
            remote_eof_observed=item.remote_eof, upstream_write_shutdown=item.write_closed,
            tcp_completion_evidence=(outcome == "tcp_eof" and item.client_eof and item.remote_eof
                                     and not item.outgoing), application_success_inferred=False)'''
    old_order = '''            for identity, item in list(connections.items()):
                if now - item.last_progress >= limits.idle_seconds:'''
    new_order = '''            for identity, item in list(connections.items()):
                if item.client_eof and item.remote_eof and not item.outgoing:
                    finish_connection(identity, "tcp_eof")
                    continue
                if now - item.last_progress >= limits.idle_seconds:'''
    for before, after in ((old_record, new_record), (old_order, new_order)):
        if source.count(before) != 1:
            raise ValueError("Underlying TCP relay source changed; review the exact patch before binding")
        source = source.replace(before, after)
    compiled = {}
    exec(compile(source, __file__+":observed-eof-relay", "exec"), namespace, compiled)
    namespace["relay_many"] = compiled["relay_many"]
    namespace["__file__"] = __file__
    namespace["source_repair_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    result = ModuleType(__name__+".private_transport")
    result.__dict__.update(namespace)
    return result

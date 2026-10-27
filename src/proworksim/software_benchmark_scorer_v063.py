"""Independent v063 rescore of one locked candidate; no active v062 mutations."""

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path
import threading
import time

from . import software_benchmark_rescore_policy_v063 as policy
from . import software_benchmark_grading_environment_v062 as environment
from . import software_benchmark_grading_environment_v058 as archive
from . import software_benchmark_scorer_v054 as base
from . import software_benchmark_scorer_v056 as original_scorer
from .software_benchmark_scorer_v058 import validate_runtime_relocation
from . import software_benchmark_diff_diagnostics_v063 as diagnostics
from .software_benchmark_scorer_r5_v054 import check_candidate
from .software_benchmark_scorer_r6_v055 import cpus
from .software_benchmark_baseline_v054 import validate_mapping
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
VERSION = "v063-offline-capability-official-scorer-r1"
LIMITS = {
    "network_mode": "none",
    "nano_cpus": 4000000000,
    "memory_bytes": 16 * 1024**3,
    "pids_limit": 512,
    "timeout_seconds": 1800,
}


def load(ref):
    return json.loads(checked(ref).read_bytes())


def installation_manifest():
    return {
        "version": VERSION,
        "parent": original_scorer.installation_manifest(),
        "adapter": reference(__file__),
        "guard": reference(policy.__file__),
        "diagnostic_decode_adapter": reference(diagnostics.__file__),
        "diagnostic_upstream_sha256": diagnostics.UPSTREAM_SHA256,
        "archive_adapter": reference(archive.__file__),
        "environment_router": reference(environment.__file__),
        "offline_requests_adapter": reference(environment.offline.__file__),
        "real_tls_requests_adapter": reference(environment.tls.__file__),
        "requests_capabilities_by_task": {task: environment.capabilities(task) for task in sorted(environment.TASKS)},
        "limits": LIMITS,
        "cap_add": [],
        "cap_drop": ["ALL"],
        "no_new_privileges": True,
        "official_tests_and_scoring_rules_changed": False,
        "container_lifecycle_adapter": "owned fresh objects only; no pre-existing container cleanup; remove SYS_ADMIN default",
        "official_file_transfer": "byte-identical patch/eval script; root-owned archive metadata",
        "public_network": False,
        "host_namespace_mount_or_daemon_operations": False,
    }


def validate_base(config):
    frozen = load(config["scorer_request_base"]["scorer_manifest"])
    validate_runtime_relocation(frozen, original_scorer.installation_manifest())
    return frozen


def _planned(request):
    plan = load(request["plan"])
    if request["plan"] != reference(policy.PLAN_FILE):
        raise ValueError("Scoring belongs to another capability plan")
    key = request["resource_key"]
    resource = plan["resources"].get(key)
    if not resource or resource["role"] not in {"score", "control"}:
        raise ValueError("Unexpected grading resource identity")
    config = load(request["configuration"])
    task = resource["instance_id"]
    if config["instance_id"] != task:
        raise ValueError("Original configuration belongs to another task")
    if resource["role"] == "control":
        if request["configuration"] != plan["environments"][task]["configuration"]:
            raise ValueError("Control original configuration differs")
        if (
            request.get("patch_kind") != resource["patch_kind"]
            or request.get("candidate_lock") is not None
        ):
            raise ValueError("Control patch kind or model-candidate boundary differs")
    else:
        row = next(r for r in plan["rows"] if r["slot_id"] == resource["slot_id"])
        if (
            request["configuration"] != row["configuration"]
            or request.get("measurement_kind") != row["measurement_kind"]
            or request.get("slot_id") != row["slot_id"]
            or request.get("source_slot_id") != row["source_slot_id"]
        ):
            raise ValueError("Candidate differs from the original/capability slot mapping")
    return plan, resource, config


def validate_request(request):
    if request.get("version") != VERSION or request.get("limits") != LIMITS:
        raise ValueError("Unrecognized fixed v063 scoring request")
    plan, resource, config = _planned(request)
    if resource["role"] == "score":
        original_request = load(plan["original_score_request"])
        if (request.get("resource_key") != policy.SCORE_KEY
                or any(request.get(key) != original_request.get(key) for key in (
                    "candidate_lock", "generation_result", "configuration", "slot_id",
                    "source_slot_id", "measurement_kind"))):
            raise ValueError("Only the exact original score-29 candidate may be rescored")
    policy.require_v063_allowed(
        "v063.control" if resource["role"] == "control" else "v063.score",
        instance_id=resource["instance_id"],
    )
    validate_base(config)
    environment.validate_request(request, resource["instance_id"])
    if load(request["scorer_manifest"]) != installation_manifest():
        raise ValueError("Capability scorer changed after freezing")
    folder = Path(request["directory"]).resolve()
    expected = policy.GRADING_ROOT / request["resource_key"]
    admitted_cpu_sets = {policy.cpu_set("grader", 0)}
    if folder != expected or request["cpuset_cpus"] not in admitted_cpu_sets:
        raise ValueError("Scoring output or four-CPU affinity differs from plan")
    if resource["role"] == "score":
        original = config["scorer_request_base"]
        lock = load(request["candidate_lock"])
        exported = lock["patch_receipt"]
        check_candidate(
            {
                "preparation_only": False,
                "arm": "REF",
                "native_candidate_lock": request["candidate_lock"],
                "instance_id": config["instance_id"],
                "candidate_tree_sha256": lock["tree_sha256"],
                "baseline_tree_sha256": exported["base_tree_sha256"],
                "patch": exported["patch"],
            }
        )
        if (
            lock["slot"]["slot_id"] != request["slot_id"]
            or lock["slot"]["condition_id"] != config["condition_id"]
            or lock["slot"]["seed"] != config["seed"]
        ):
            raise ValueError("Candidate is not the uniquely closed planned seed/condition")
        checked(exported["patch"]).read_bytes().decode("utf-8", "strict")
        validate_qualification(request["qualification"], config, request["plan"])
        result = load(request["generation_result"])
        quiet_ref = result.get("quiescence")
        if not isinstance(quiet_ref, dict) or set(quiet_ref) != {"path", "bytes", "sha256"}:
            raise ValueError("Fresh generation requires immutable independent cleanup proof")
        quiet = load(quiet_ref)
        if (result.get("status") != "closed" or result.get("candidate_lock") != request["candidate_lock"]
                or result.get("slot_id") != request["slot_id"]
                or result.get("source_slot_id") != request["source_slot_id"]
                or result.get("measurement_kind") != "capability_probe"
                or result.get("configuration") != request["configuration"]
                or quiet.get("quiescent") is not True or quiet.get("cleanup_errors") != []
                or quiet.get("create_result_unknown") is not False):
            raise ValueError("Fresh candidate lacks its unique capability-probe terminal record")
        if original["image"]["image_id"] != resource["image_id"]:
            raise ValueError("Original task image changed")
    return plan, resource, config


def validate_options(options, image_id):
    if options.get("image") != image_id:
        raise ValueError("Only the original fixed grading image may run")
    forbidden = (
        "volumes",
        "mounts",
        "devices",
        "device_requests",
        "volumes_from",
        "links",
        "ports",
        "publish_all_ports",
        "network",
        "networking_config",
        "dns",
        "dns_search",
        "dns_opt",
        "extra_hosts",
        "sysctls",
        "runtime",
        "group_add",
        "tmpfs",
        "cgroup_parent",
        "device_cgroup_rules",
        "storage_opt",
        "use_config_proxy",
    )
    if any(options.get(key) for key in forbidden) or options.get("privileged"):
        raise ValueError("Grader cannot receive host mounts, devices or networking overrides")
    if options.get("cap_add") not in (None, [], ["SYS_ADMIN"]):
        raise ValueError("Unexpected added capabilities")
    for name in ("pid_mode", "ipc_mode", "uts_mode", "cgroupns"):
        if options.get(name) not in (None, "", "private"):
            raise ValueError("Grader must use private namespaces")
    if options.get("userns_mode") not in (None, "") or options.get("network_mode") not in (
        None,
        "none",
    ):
        raise ValueError("Grader namespace/network override forbidden")


def validate_attrs(attrs, observation):
    task = observation["mapping"]["instance_id"]
    if task in environment.TASKS:
        adapter = environment.provider(task)
        environment.offline.validate_container_config(attrs, observation, LIMITS, adapter.PROFILES[task])
        labels = attrs.get("Config", {}).get("Labels") or {}
        if any(labels.get(key) != value for key, value in observation["labels"].items()):
            raise ValueError("Requests grader ownership labels differ")
        return
    host = attrs["HostConfig"]
    if (
        attrs.get("Image") != observation["image_id"]
        or host.get("NetworkMode") != "none"
        or host.get("CapAdd") not in (None, [])
        or host.get("CapDrop") != ["ALL"]
        or host.get("SecurityOpt") != ["no-new-privileges:true"]
        or host.get("Privileged")
        or host.get("NanoCpus") != LIMITS["nano_cpus"]
        or host.get("Memory") != LIMITS["memory_bytes"]
        or host.get("MemorySwap") != LIMITS["memory_bytes"]
        or host.get("PidsLimit") != LIMITS["pids_limit"]
        or host.get("CpusetCpus") != observation["cpuset_cpus"]
        or attrs.get("Mounts")
        or any(
            host.get(key)
            for key in (
                "Binds",
                "Mounts",
                "Devices",
                "DeviceRequests",
                "PortBindings",
                "Links",
                "ExtraHosts",
                "Sysctls",
                "VolumesFrom",
            )
        )
    ):
        raise ValueError("Actual grader resource or isolation settings differ")
    for key in ("PidMode", "IpcMode", "UTSMode", "CgroupnsMode"):
        if host.get(key) not in (None, "", "private"):
            raise ValueError("Actual grader shares a host or foreign namespace")
    labels = attrs.get("Config", {}).get("Labels") or {}
    if any(labels.get(k) != v for k, v in observation["labels"].items()):
        raise ValueError("Grader ownership labels differ")


class ObservedContainer(archive.EnvironmentContainer):
    def start(self, *args, **kwargs):
        policy.require_v063_allowed(
            "v063.grader.start", instance_id=self.preparation["mapping"]["instance_id"]
        )
        self.delegate.reload()
        validate_attrs(self.delegate.attrs, self.preparation)
        result = base.PreparationObservedContainer.start(self, *args, **kwargs)
        validate_attrs(self.delegate.attrs, self.preparation)
        path = Path(self.preparation["path"])
        observed = json.loads(path.read_bytes())
        if (
            observed["head_git_tree"] != self.preparation["mapping"]["official_tree"]
            or observed["working_tree_clean"] is not True
        ):
            raise ValueError("Official initial baseline is not the pinned clean tree")
        source = "import os,json; print(json.dumps({'namespaces':{k:os.stat('/proc/self/ns/'+k).st_ino for k in ('net','mnt','pid','ipc')},'cpus':sorted(os.sched_getaffinity(0))}))"
        inside = json.loads(
            archive.checked_exec(
                self.delegate,
                [self.preparation["mapping"]["public_python"], "-c", source],
                timeout_note="Private grader boundary",
            )
        )
        host = {key: os.stat("/proc/self/ns/" + key).st_ino for key in archive.NAMESPACES}
        if inside["cpus"] != cpus(self.preparation["cpuset_cpus"]):
            raise ValueError("Actual grader CPU affinity differs")
        observed.update(
            namespace_evidence=archive.namespace_evidence(inside["namespaces"], host),
            source_image_id=self.preparation["image_id"],
            candidate_or_official_tests_changed=False,
            actual_cap_add=[],
            actual_cap_drop=["ALL"],
            effective_network_mode="none",
            resource_key=self.preparation["resource_key"],
        )
        path.write_bytes(base.canonical(observed))
        return result


class Containers(base.LocalContainers):
    def __init__(self, delegate, image_id, observation, tracking):
        super().__init__(delegate, image_id, LIMITS)
        self.observation, self.tracking = observation, tracking

    def get(self, name):
        # The upstream pre-create "ghost cleanup" may not inspect/remove existing objects.
        import docker

        raise docker.errors.NotFound("v063 never reuses a pre-existing container")

    def create(self, **options):
        policy.require_v063_allowed(
            "v063.grader.create", instance_id=self.observation["mapping"]["instance_id"]
        )
        validate_options(options, self.image_id)
        claim_ref = policy.claim_resource(self.observation["resource_key"])
        claim = load(claim_ref)
        labels = {
            "proworksim.owner": VERSION,
            "proworksim.resource": claim["key"],
            "proworksim.plan": claim["plan"]["sha256"],
        }
        options.update(
            name=claim["docker_name"],
            labels=labels,
            user="root",
            network_mode="none",
            cap_add=[],
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            privileged=False,
            ipc_mode="private",
            entrypoint=[],
            command=["/bin/sh", "-c", "sleep 3600"],
            mem_limit=LIMITS["memory_bytes"],
            memswap_limit=LIMITS["memory_bytes"],
            nano_cpus=LIMITS["nano_cpus"],
            pids_limit=LIMITS["pids_limit"],
            cpuset_cpus=self.observation["cpuset_cpus"],
        )
        task = self.observation["mapping"]["instance_id"]
        options["cap_add"] = environment.capabilities(task)
        if task in environment.TLS_TASKS:
            options.update(extra_hosts={"httpbin.org": "127.0.0.1"},
                           environment=environment.tls.fixture_environment(options.get("environment")))
        elif task in environment.OFFLINE_TASKS:
            options["environment"] = environment.offline.fixture_environment(
                environment.offline.PROFILES[task], options.get("environment"))
        self.tracking.update(claim=claim_ref, create_result_unknown=True)
        self.tracking["create_identity"] = {"name": claim["docker_name"], "labels": labels, "image_id": self.image_id}
        self.observation["labels"] = labels
        began = time.monotonic()
        try:
            container = self.delegate.create(**options)
        except Exception:
            try:
                owned = self.delegate.get(claim["docker_name"])
                owned.reload()
                if owned.attrs.get("Image") == self.image_id and all(
                    (owned.attrs.get("Config", {}).get("Labels") or {}).get(k) == v
                    for k, v in labels.items()
                ):
                    self.tracking["owned_container_ids"].append(owned.id)
                    self.tracking["create_result_unknown"] = False
            except Exception:
                pass
            raise
        self.tracking["owned_container_ids"].append(container.id)
        self.tracking["create_result_unknown"] = False
        container.reload()
        validate_attrs(container.attrs, self.observation)

        def expire():
            self.tracking["deadline_reached"] = True
            try:
                container.stop(timeout=5)
            except Exception as error:
                self.tracking.setdefault("watchdog_errors", []).append(str(error))

        timer = threading.Timer(max(0, 3600 - (time.monotonic() - began)), expire)
        timer.daemon = True
        self.tracking["deadline_timer"] = timer
        timer.start()
        if task in environment.TLS_TASKS:
            wrapper = environment.tls.EnvironmentContainer(container, self.observation, LIMITS, self.tracking)
            self.tracking["environment_container"] = wrapper
            return wrapper
        if task in environment.OFFLINE_TASKS:
            return environment.offline.EnvironmentContainer(container, self.observation, LIMITS)
        return ObservedContainer(container, self.observation, LIMITS)


def cleanup(request, tracking):
    transport_errors = environment.tls.cleanup_transport(tracking) if tracking.get("environment_container") else []
    timer = tracking.get("deadline_timer")
    if timer:
        timer.cancel()
        timer.join(timeout=10)
    proof = original_scorer.cleanup_scoring(request, tracking)
    proof.update(
        version=VERSION,
        resource_key=request["resource_key"],
        deadline_reached=tracking.get("deadline_reached", False),
    )
    proof["cleanup_errors"].extend(tracking.get("watchdog_errors", []))
    proof["cleanup_errors"].extend(transport_errors)
    proof["transport_result"] = tracking.get("transport_result")
    if timer and timer.is_alive():
        proof["cleanup_errors"].append("Container deadline timer remains alive")
    proof["quiescent"] = proof["quiescent"] and not proof["cleanup_errors"]
    if tracking.get("claim"):
        policy.release_resource(tracking["claim"], quiescent=proof["quiescent"])
    return proof


def score_request(request):
    _, resource, config = validate_request(request)
    folder = Path(request["directory"])
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "quiescence.json").exists():
        raise ValueError("A grading attempt is never replayed")
    tracking = {
        "phase": "before_admission",
        "owned_container_ids": [],
        "create_result_unknown": False,
        "client": None,
    }
    previous = {}

    def interrupted(signum, frame):
        tracking["cancel_requested"] = True
        if tracking.get("phase") != "cleanup":
            raise InterruptedError("Owned v063 grader cancellation requested")

    if threading.current_thread() is threading.main_thread():
        previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        return _score(request, resource, config, tracking)
    finally:
        tracking["phase"] = "cleanup"
        try:
            write_new(folder / "quiescence.json", cleanup(request, tracking))
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def _score(request, resource, config, tracking):
    original = config["scorer_request_base"]
    instance = base.read_local_dataset(original["dataset"])[config["instance_id"]]
    mapping = validate_mapping(
        load(original["baseline_mapping"]), instance=instance, image=original["image"]
    )
    if resource["role"] == "control":
        patch = (instance["patch"] if resource["patch_kind"] == "gold" else "").encode("utf-8")
    else:
        lock = load(request["candidate_lock"])
        patch = checked(lock["patch_receipt"]["patch"]).read_bytes()
    identity = {
        "version": VERSION,
        "request": reference(Path(request["directory"]) / "request.json"),
        "resource_key": request["resource_key"],
        "instance_id": config["instance_id"],
        "configuration": request["configuration"],
        "candidate_lock": request.get("candidate_lock"),
        "measurement_kind": request.get("measurement_kind", "environment_control"),
        "source_slot_id": request.get("source_slot_id"),
        "slot_id": request.get("slot_id"),
        "condition_id": config["condition_id"],
        "patch_kind": request.get("patch_kind"),
        "patch_sha256": base.sha256(patch),
        "patch_bytes": len(patch),
        "plan": request["plan"],
        "image": original["image"],
        "dataset": original["dataset"],
        "baseline_mapping": original["baseline_mapping"],
        "scorer_manifest": request["scorer_manifest"],
        "qualification": request.get("qualification"),
        "limits": LIMITS,
        "cpuset_cpus": request["cpuset_cpus"],
        "model_calls": 0,
        "actor_feedback": False,
        "environment_revision": request.get("environment_revision"),
        "network_resolution": request.get("network_resolution"),
    }
    run_id = "v063-" + request["resource_key"] + "-" + base.sha256(base.canonical(identity))[:24]
    folder = Path(request["directory"])
    output = folder / "official-output"
    output.mkdir(mode=0o700, exist_ok=False)
    write_new(output / "identity.json", identity)
    socket = Path(original["docker_socket"]).resolve()
    if not socket.is_socket():
        raise ValueError("Existing project Docker socket unavailable")
    if config["instance_id"] in environment.TLS_TASKS:
        environment.tls.install_socket_guard(socket, load(request["network_resolution"]))
    else:
        base.install_offline_guard(socket)
    import docker
    from swebench.harness import run_evaluation as harness
    from swebench.harness.utils import make_test_spec

    spec = make_test_spec(instance)
    if any(spec.image_assets.values()):
        raise ValueError("No implicit external test assets are admitted")
    os.umask(0o077)
    os.chdir(output)
    os.environ["DOCKER_HOST"] = "unix://" + str(socket)
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        os.environ.pop(key, None)
    os.environ["PATH"] = str(checked(original["docker_cli"]).parent) + ":/usr/bin:/bin"
    spec.image = original["image"]["image_id"]
    client = docker.DockerClient(base_url=os.environ["DOCKER_HOST"], timeout=1800)
    tracking.update(client=client, phase="official_scoring")
    observation = {
        "path": str(output / "initial-container.json"),
        "mapping": mapping,
        "base_commit": mapping["official_head"],
        "image_id": spec.image,
        "cpuset_cpus": request["cpuset_cpus"],
        "resource_key": request["resource_key"],
        "environment_revision": request.get("environment_revision"),
        "network_resolution": request.get("network_resolution"),
    }
    restricted = base.LocalDocker(client, spec.image, LIMITS)
    restricted.containers = Containers(client.containers, spec.image, observation, tracking)
    prediction = {
        "instance_id": config["instance_id"],
        "model_name_or_path": request["resource_key"],
        "model_patch": patch.decode("utf-8"),
    }
    evaluation, repair_provenance = diagnostics.make_repaired_run_instance(
        harness, output / "raw-diff-diagnostics"
    )
    write_new(output / "diagnostic-repair.json", repair_provenance)
    run_instance = evaluation
    if config["instance_id"] in environment.TLS_TASKS:
        def evaluation(*args, **kwargs):
            return environment.tls.run_official(run_instance, *args, tracking=tracking, **kwargs)
    result = evaluation(
        spec,
        prediction,
        restricted,
        run_id,
        timeout=1800,
        rewrite_reports=False,
        skip_patch=not patch,
        task_repo=None,
    )
    report = result[1].get(config["instance_id"], {}) if result else {}
    known = (
        result is not None
        and report.get("patch_successfully_applied") is True
        and not report.get("infra_failure", False)
        and type(report.get("resolved")) is bool
        and not tracking.get("deadline_reached")
    )
    if config["instance_id"] in environment.TLS_TASKS:
        transport = environment.tls.finish_transport(tracking)
        known = known and transport.get("ok") is True
    receipt = {
        "version": VERSION,
        "resource_key": request["resource_key"],
        "run_id": run_id,
        "instance_id": config["instance_id"],
        "slot_id": request.get("slot_id"),
        "source_slot_id": request.get("source_slot_id"),
        "condition_id": config["condition_id"],
        "measurement_kind": identity["measurement_kind"],
        "patch_kind": request.get("patch_kind"),
        "status": "official_report" if known else "technical_unknown",
        "resolved": report.get("resolved") if known else None,
        "official_result": result,
        "identity": reference(output / "identity.json"),
        "model_calls": 0,
        "actor_feedback": False,
        "candidate_changed": False,
        "transport_result": tracking.get("transport_result"),
        "diagnostic_repair": reference(output / "diagnostic-repair.json"),
    }
    write_new(folder / "receipt.json", receipt)
    return receipt


def validate_qualification(ref, config, plan_ref):
    value = load(ref)
    task = config["instance_id"]
    if (
        value.get("version") != VERSION
        or value.get("instance_id") != task
        or value.get("passed") is not True
        or value.get("plan") != plan_ref
        or len(value.get("controls", [])) != 2
    ):
        raise ValueError("This task lacks an independent gold/empty qualification")
    seen = set()
    for item in value["controls"]:
        kind = item["patch_kind"]
        if kind not in {"gold", "empty"} or kind in seen:
            raise ValueError("Duplicate or unexpected task control")
        seen.add(kind)
        receipt, quiet, completion = (
            load(item[key]) for key in ("receipt", "quiescence", "completion")
        )
        identity = load(receipt["identity"])
        observed = load(item["initial_container"])
        expected_key = "control-" + task + "-" + kind
        folder = policy.GRADING_ROOT / expected_key
        for key in ("receipt", "quiescence", "completion"):
            if Path(item[key]["path"]).resolve() != folder / (key + ".json"):
                raise ValueError("Control evidence borrowed from another endpoint")
        if (
            receipt.get("version") != VERSION
            or receipt.get("status") != "official_report"
            or receipt.get("resource_key") != expected_key
            or receipt.get("instance_id") != task
            or identity.get("plan") != plan_ref
            or identity.get("resource_key") != expected_key
            or identity.get("dataset") != config["scorer_request_base"]["dataset"]
            or identity.get("image") != config["scorer_request_base"]["image"]
            or identity.get("baseline_mapping") != config["scorer_request_base"]["baseline_mapping"]
            or identity.get("scorer_manifest") != reference(policy.COORDINATOR_RUN_ROOT / "scorer-manifest.json")
            or identity.get("limits") != LIMITS
            or identity.get("patch_kind") != kind
            or identity.get("actor_feedback") is not False
            or identity.get("model_calls") != 0
            or receipt.get("actor_feedback") is not False
            or receipt.get("model_calls") != 0
            or quiet.get("resource_key") != expected_key
            or quiet.get("quiescent") is not True
            or quiet.get("cleanup_errors") != []
            or quiet.get("create_result_unknown") is not False
            or quiet.get("deadline_reached") is not False
            or completion.get("returncode") != 0
        ):
            raise ValueError("Control identity, baseline, runtime completion or cleanup is invalid")
        if Path(item["initial_container"]["path"]).resolve() != folder / "official-output/initial-container.json":
            raise ValueError("Initial container evidence belongs to another control")
        environment.validate_request(identity, task)
        mapping = load(config["scorer_request_base"]["baseline_mapping"])
        if (observed.get("head_git_tree") != mapping["official_tree"]
                or observed.get("working_tree_clean") is not True
                or observed.get("effective_network_mode") != "none"
                or observed.get("namespace_evidence", {}).get("all_distinct") is not True):
            raise ValueError("Gold/empty baseline or namespace identity is incomplete")
        if task in environment.TASKS:
            if (observed.get("environment_revision") != identity["environment_revision"]
                    or observed.get("task_files_changed") is not False
                    or observed.get("timeout_route", {}).get("real_connect_timeout") is not True
                    or observed.get("actual_capabilities") != environment.capabilities(task)
                    or observed.get("actual_dropped_capabilities") != ["ALL"]):
                raise ValueError("Requests fixture identity or private capabilities differ")
        if task in environment.TLS_TASKS:
            from .software_benchmark_grading_qualification_v060 import validate_transport_evidence
            validate_transport_evidence(receipt, quiet, observed, identity, folder)
        report = receipt["official_result"][1][task]
        if report.get("patch_successfully_applied") is not True or report.get("infra_failure"):
            raise ValueError("Control did not complete trustworthy official scoring")
        if kind == "gold":
            if receipt.get("resolved") is not True or report.get("resolved") is not True:
                raise ValueError("Official reference repair did not pass")
        elif (
            receipt.get("resolved") is not False
            or report.get("resolved") is not False
            or not report.get("tests_status", {}).get("FAIL_TO_PASS", {}).get("failure")
        ):
            raise ValueError("Empty baseline did not fail the target test")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    result = score_request(json.loads(parser.parse_args().request.read_bytes()))
    print(json.dumps({k: result[k] for k in ("resource_key", "status", "resolved")}))


if __name__ == "__main__":
    main()

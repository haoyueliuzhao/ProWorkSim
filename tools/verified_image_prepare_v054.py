#!/usr/bin/env python3
"""Prepare pinned Verified images in the project daemon, with no model execution."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import threading
import time

try:
    from .domestic_registry_blob import download_blob
    from .verified_image_metadata_v054 import load_inventory
    from .verified_registry_ranges_v054 import RangePool
except ImportError:
    from domestic_registry_blob import download_blob
    from verified_image_metadata_v054 import load_inventory
    from verified_registry_ranges_v054 import RangePool

ROOT = Path(__file__).resolve().parents[1]
SOCKET = "unix://" + str(ROOT / "runs/software-panel-v053/docker/docker.sock")
DOCKER = "/usr/bin/docker"
GiB = 1024**3


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def file_stat(path):
    item = path.stat()
    return {"device": item.st_dev, "inode": item.st_ino, "bytes": item.st_size,
            "mtime_ns": item.st_mtime_ns, "ctime_ns": item.st_ctime_ns}


def cached_blob_proof(blob):
    path = Path(blob["path"])
    receipt_path = path.with_name(path.name + ".verified.json")
    if not path.is_file() or not receipt_path.is_file():
        return None
    receipt = json.loads(receipt_path.read_bytes())
    identity = file_stat(path)
    expected_identity = {
        "dev": identity["device"], "ino": identity["inode"], "size": identity["bytes"],
        "mtime_ns": identity["mtime_ns"], "ctime_ns": identity["ctime_ns"],
    }
    if (receipt.get("expected_sha256") != blob["digest"].split(":")[1]
            or receipt.get("expected_bytes") != blob["bytes"]
            or receipt.get("file_identity") != expected_identity):
        return None
    return {"path": str(path), "stat": identity, "bytes": blob["bytes"],
            "sha256": receipt["expected_sha256"], "proof": str(receipt_path),
            "reused_v054": True}


def verified_prior_layers():
    """Reuse existing complete v053 proofs by identity, without reading old layers."""
    result = {}
    for relative in (
        "prefetch-ranks09-24-v1/layer-index.partial.json",
        "prefetch-ranks25-32-v1/layer-index.partial.json",
    ):
        source = ROOT / "runs/software-panel-v053" / relative
        if not source.exists():
            continue
        value = json.loads(source.read_bytes())
        if value.get("available_layer_digests_verified") is not True:
            continue
        for digest, proof in value["layers"].items():
            path = Path(proof["path"])
            if (path.is_file() and file_stat(path) == proof["stat"]
                    and proof["bytes"] == proof["stat"]["bytes"]):
                result["sha256:" + digest] = {
                    "path": str(path), "stat": proof["stat"], "sha256": digest,
                    "bytes": proof["bytes"], "proof": str(source), "reused_v053": True,
                }
    return result


def merged_official(official_root, expected_sha):
    rows = {}
    references = []
    for path in sorted(official_root.rglob("summary.json")):
        report = json.loads(path.read_bytes())
        if report.get("schema") != "proworksim.verified-image-metadata.v054":
            continue
        if report["source"] != "official" or report["inventory_sha256"] != expected_sha:
            raise ValueError("official metadata source/inventory differs")
        references.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in report["images"]:
            if row["instance_id"] in rows:
                raise ValueError("duplicate official metadata for instance")
            rows[row["instance_id"]] = row
    if len(rows) != 500 or any(row["status"] != "manifest_verified" for row in rows.values()):
        raise ValueError("require all 500 successful current official manifest identities")
    return rows, references


def make_plan(inventory, official_root, mirror_summary, cache):
    rows, identity = load_inventory(inventory)
    official, refs = merged_official(official_root, identity)
    mirror = json.loads(mirror_summary.read_bytes())
    if mirror["source"] != "mirror" or mirror["inventory_sha256"] != identity:
        raise ValueError("mirror metadata source/inventory differs")
    mirrored = {row["instance_id"]: row for row in mirror["images"]}
    if len(mirrored) != 500:
        raise ValueError("require all 500 mirror outcomes")
    blobs, images = {}, []
    for row in sorted(rows, key=lambda item: item["instance_id"]):
        fixed, delivered = official[row["instance_id"]], mirrored[row["instance_id"]]
        for key in ("image_name", "tag", "base_commit", "repo"):
            if fixed[key] != row[key] or delivered[key] != row[key]:
                raise ValueError("manifest identity differs from task inventory")
        mirror_matches = None
        if delivered["status"] == "manifest_verified":
            for key in ("top_manifest_digest", "manifest_digest", "config_digest", "config", "layers"):
                if fixed[key] != delivered[key]:
                    raise ValueError("mirror differs from current official identity: " + row["instance_id"])
            mirror_matches = True
        for descriptor in [fixed["config"], *fixed["layers"]]:
            digest = descriptor["digest"]
            if digest in blobs and blobs[digest]["bytes"] != descriptor["size"]:
                raise ValueError("digest size mismatch")
            blobs.setdefault(digest, {
                "digest": digest, "bytes": descriptor["size"], "image_name": row["image_name"],
                "path": str(cache / (digest.split(":")[1] + ".blob")),
            })
        images.append({
            **row, "top_manifest_digest": fixed["top_manifest_digest"],
            "manifest_digest": fixed["manifest_digest"], "config_digest": fixed["config_digest"],
            "config": fixed["config"], "layers": fixed["layers"], "image_id": None,
            "platform": None, "status": "pinned_not_loaded", "environment_ready": False,
            "mirror_manifest_status": delivered["status"],
            "mirror_matches_official": mirror_matches,
            "mirror_manifest_error": delivered.get("error"),
            "blob_delivery_identity": "Official immutable descriptors, SHA256 and size required.",
        })
    prior = verified_prior_layers()
    reused = {}
    for digest, blob in blobs.items():
        if digest in prior and prior[digest]["bytes"] == blob["bytes"]:
            blob["path"] = prior[digest]["path"]
            reused[digest] = prior[digest]
        else:
            proof = cached_blob_proof(blob)
            if proof is not None:
                reused[digest] = proof
    return {
        "schema": "proworksim.verified-image-preparation.v054",
        "inventory_sha256": identity, "official_metadata_refs": refs,
        "mirror_summary_sha256": hashlib.sha256(mirror_summary.read_bytes()).hexdigest(),
        "docker_socket": SOCKET, "planned_images": 500, "images": images,
        "blobs": blobs, "reused_blob_proofs": reused,
        "unique_blob_count": len(blobs),
        "unique_compressed_blob_bytes": sum(blob["bytes"] for blob in blobs.values()),
        "reused_compressed_blob_bytes": sum(proof["bytes"] for proof in reused.values()),
        "required_network_payload_bytes_upper_bound": sum(
            blob["bytes"] for digest, blob in blobs.items() if digest not in reused),
        "uncompressed_disk_bytes": None,
        "uncompressed_disk_note": "Manifest does not specify inflated layer sizes; live disk gates apply.",
        "model_calls": 0, "gpu_device_requests": 0, "created_at_utc": now(),
    }


def docker(*args, timeout=120, check=True):
    environment = {key: value for key, value in os.environ.items()
                   if key.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    environment.update(NO_PROXY="*", no_proxy="*", DOCKER_HOST=SOCKET)
    return subprocess.run(
        [DOCKER, "--host", SOCKET, *args], capture_output=True, text=True,
        timeout=timeout, check=check, env=environment)


def daemon_identity():
    value = json.loads(docker("info", "--format", "{{json .}}").stdout)
    expected = ROOT / "runs/software-panel-v053/docker/data"
    if value["DockerRootDir"] != str(expected):
        raise ValueError("Docker service is not the project private daemon")
    return {key: value[key] for key in (
        "ID", "DockerRootDir", "ServerVersion", "Architecture", "OSType")}


def disk_gate(path, minimum_free, additional=0):
    free = shutil.disk_usage(path).free
    if free < minimum_free + additional:
        raise RuntimeError("disk_reserve_gate")
    return free


def stream_load(image, blobs, proof, folder, minimum_free):
    expected = image["config_digest"]
    inspection = docker("image", "inspect", expected, check=False)
    if inspection.returncode == 0:
        item = json.loads(inspection.stdout)[0]
        if item["Id"] != expected:
            raise ValueError("existing image ID differs")
        return {"image_id": expected, "reused_local_image": True,
                "platform": {"os": item["Os"], "architecture": item["Architecture"]}}
    disk_gate(folder, minimum_free, max(layer["size"] for layer in image["layers"]) * 3)
    entries = [image["config"], *image["layers"]]
    for descriptor in entries:
        digest = descriptor["digest"]
        if file_stat(Path(blobs[digest]["path"])) != proof[digest]["stat"]:
            raise ValueError("verified blob changed before Docker load")
    config = json.loads(Path(blobs[expected]["path"]).read_bytes())
    if config["os"] != "linux" or config["architecture"] != "amd64":
        raise ValueError("config platform is not linux/amd64")
    if len(config["rootfs"]["diff_ids"]) != len(image["layers"]):
        raise ValueError("config diff IDs and layers differ")
    tag = image["image_name"] + ":" + image["tag"]
    manifest = [{
        "Config": expected.split(":")[1] + ".json", "RepoTags": [tag],
        "Layers": ["layers/" + layer["digest"].split(":")[1] + "/layer.tar"
                   for layer in image["layers"]],
    }]
    log_path = folder / "loads" / (image["instance_id"] + ".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [DOCKER, "--host", SOCKET, "load"], stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT)
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                body = json.dumps(manifest, separators=(",", ":")).encode()
                info = tarfile.TarInfo("manifest.json")
                info.size, info.mode = len(body), 0o644
                archive.addfile(info, io.BytesIO(body))
                names = [manifest[0]["Config"], *manifest[0]["Layers"]]
                for descriptor, name in zip(entries, names, strict=True):
                    path = Path(blobs[descriptor["digest"]]["path"])
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = descriptor["size"], 0o644
                    with path.open("rb") as source:
                        archive.addfile(info, source)
            process.stdin.close()
            status = process.wait(timeout=1200)
            if status:
                raise RuntimeError("docker_load_failed")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
    item = json.loads(docker("image", "inspect", tag).stdout)[0]
    if item["Id"] != expected or item["Os"] != "linux" or item["Architecture"] != "amd64":
        raise ValueError("loaded image identity/platform mismatch")
    return {"image_id": expected, "reused_local_image": False,
            "platform": {"os": item["Os"], "architecture": item["Architecture"]},
            "load_log": str(log_path)}


PREFLIGHT = r"""
import glob, json, os, subprocess, sys
expected, repo = sys.argv[1:]
def git(*args):
    r=subprocess.run(["git","-c","safe.directory=/testbed","-C","/testbed",*args],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    return r.returncode,r.stdout.strip()
rc,head=git("rev-parse","HEAD")
tree_rc,tree=git("rev-parse","HEAD^{tree}")
status_rc,status=git("status","--porcelain")
base_exists=git("cat-file","-t",expected)==(0,"commit")
future=git("rev-list","--count","--all","--not",expected) if base_exists else (1,"")
reflog_future=git("rev-list","--count","--reflog","--not",expected) if base_exists else (1,"")
fsck_rc,fsck=git("fsck","--connectivity-only","--no-reflogs","--unreachable")
unreachable=[line.split()[2] for line in fsck.splitlines()
             if line.startswith("unreachable commit ") and len(line.split())==3]
nonancestor=sum(git("merge-base","--is-ancestor",item,expected)[0]!=0
                for item in unreachable) if base_exists and fsck_rc==0 else None
remote=git("remote")
top=repo.rsplit("/",1)[-1].replace("-","_")
aliases={"scikit_learn":["scikit-learn","scikit_learn","sklearn"],
         "pytest":["pytest","_pytest"],"sphinx":["sphinx"],"xarray":["xarray"]}
names=aliases.get(top,[top,top.replace("_","-")])
copies=set()
for prefix in ("/opt/miniconda3","/opt/conda","/root/miniconda3"):
    for name in names:
        for pattern in (
            prefix+"/pkgs/"+name+"-*",
            prefix+"/lib/python*/site-packages/"+name,
            prefix+"/lib/python*/site-packages/"+name+".py",
            prefix+"/envs/*/lib/python*/site-packages/"+name,
        ):
            for candidate in glob.glob(pattern):
                if not os.path.realpath(candidate).startswith("/testbed/"):
                    copies.add(candidate)
print(json.dumps({"head":head,"head_matches_base":rc==0 and head==expected,
 "head_tree":tree if tree_rc==0 else None,
 "working_tree_clean":not status if status_rc==0 else None,
 "base_commit_exists":base_exists,"future_reachable_commit_count":
 int(future[1]) if future[0]==0 and future[1].isdigit() else None,
 "future_reflog_commit_count":int(reflog_future[1])
 if reflog_future[0]==0 and reflog_future[1].isdigit() else None,
 "git_connectivity_fsck_returncode":fsck_rc,"unreachable_commit_count":len(unreachable),
 "unreachable_nonancestor_commit_count":nonancestor,
 "git_remote_names":remote[1].splitlines(),"target_package_copy_paths":sorted(copies),
 "testbed_exists":os.path.isdir("/testbed"),"inspection_python":sys.executable,
 "checks":"base HEAD/tree/clean status; all-ref, reflog and unreachable commit history; known Conda target-package paths; not full filesystem proof"}))
"""


def preflight(image, folder):
    name = "pws-v054-preflight-" + hashlib.sha256(image["instance_id"].encode()).hexdigest()[:16]
    shell = ('for py in /usr/bin/python3 /opt/miniconda3/envs/testbed/bin/python '
             '/opt/conda/envs/testbed/bin/python; do '
             '[ ! -x "$py" ] || exec "$py" -I -c "$1" "$2" "$3"; done; exit 69')
    try:
        result = docker(
            "run", "--rm", "--name", name, "--network", "none", "--read-only",
            "--label", "proworksim.v054.preflight=" + image["instance_id"],
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--cpus", "2", "--memory", "4g", "--pids-limit", "128",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", "--workdir", "/testbed",
            "--entrypoint", "/bin/bash", image["image_id"], "-c", shell, "preflight",
            PREFLIGHT, image["base_commit"], image["repo"], timeout=180, check=False)
    except subprocess.TimeoutExpired:
        inspected = docker("container", "inspect", name, check=False)
        if inspected.returncode == 0:
            container = json.loads(inspected.stdout)[0]
            if (container["Config"].get("Labels", {}).get("proworksim.v054.preflight")
                    == image["instance_id"] and container["Image"] == image["image_id"]):
                docker("container", "rm", "--force", container["Id"])
        raise
    receipt = {
        "instance_id": image["instance_id"], "image_id": image["image_id"],
        "base_commit": image["base_commit"], "repo": image["repo"],
        "preflight_policy_sha256": hashlib.sha256(PREFLIGHT.encode()).hexdigest(),
        "at_utc": now(), "returncode": result.returncode, "test_executions": 0,
        "model_calls": 0, "network": "none", "read_only": True,
    }
    if result.returncode:
        receipt.update(status="technical_unknown", stderr=result.stderr[-4000:])
    else:
        details = json.loads(result.stdout)
        receipt["details"] = details
        ready = (details["head_matches_base"]
                 and details["working_tree_clean"] is True
                 and details["future_reachable_commit_count"] == 0
                 and details["future_reflog_commit_count"] == 0
                 and details["git_connectivity_fsck_returncode"] == 0
                 and details["unreachable_nonancestor_commit_count"] == 0
                 and not details["target_package_copy_paths"])
        receipt["status"] = "bounded_preflight_passed" if ready else "requires_actor_isolation_review"
    save(folder / "preflight" / (image["instance_id"] + ".json"), receipt)
    return receipt


def execute(plan, output, *, workers, minimum_free, cdn_workers=16):
    plan["daemon"] = daemon_identity()
    free = disk_gate(output, minimum_free, plan["required_network_payload_bytes_upper_bound"])
    plan["initial_free_bytes"] = free
    plan["minimum_free_bytes"] = minimum_free
    plan["status"] = "downloading"
    save(output / "image-inventory.json", plan)
    proofs = dict(plan["reused_blob_proofs"])
    proof_path = output / "blob-proofs.json"
    if proof_path.exists():
        prior = json.loads(proof_path.read_bytes())
        for digest, proof in prior.items():
            if (digest in plan["blobs"] and Path(proof["path"]).is_file()
                    and file_stat(Path(proof["path"])) == proof["stat"]):
                proofs[digest] = proof

    stopped = threading.Event()
    range_pool = RangePool(workers=cdn_workers)
    request_start_lock = threading.Lock()
    last_request_start = [0.0]

    def fetch(item):
        if stopped.is_set():
            raise RuntimeError("preparation_stopped_after_public_fault")
        digest, blob = item
        if digest in proofs:
            return digest, proofs[digest]
        lock_path = Path(blob["path"] + ".download.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as active_lock:
            try:
                fcntl.flock(active_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fcntl.flock(active_lock, fcntl.LOCK_EX)
                completed = cached_blob_proof(blob)
                if completed is not None:
                    return digest, completed
                # The former writer has closed. A pinned, verified prefix is
                # handed to RangePool below; no active partial is read here.
            finally:
                fcntl.flock(active_lock, fcntl.LOCK_UN)
        disk_gate(output, minimum_free, blob["bytes"])
        with request_start_lock:
            delay = 8.0 - (time.monotonic() - last_request_start[0])
            if delay > 0:
                time.sleep(delay)
            last_request_start[0] = time.monotonic()
        if stopped.is_set():
            raise RuntimeError("preparation_stopped_after_public_fault")
        if blob["bytes"] >= 8 * 1024 * 1024:
            result = range_pool.download(
                blob["image_name"], digest, blob["path"], expected_bytes=blob["bytes"])
        else:
            with range_pool.slots:
                result = download_blob(
                    blob["image_name"], digest, blob["path"], expected_bytes=blob["bytes"])
        return digest, {
            "path": blob["path"], "bytes": blob["bytes"], "sha256": digest.split(":")[1],
            "stat": file_stat(Path(blob["path"])), "download": result,
        }

    plan["new_cdn_pool_limit"] = cdn_workers
    plan["registry_blob_start_interval_seconds"] = 8.0
    loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="v054-load-preflight")
    load_jobs, queued = [], set()
    plan_lock = threading.Lock()

    def finish_image(image):
        loaded = stream_load(image, plan["blobs"], proofs, output, minimum_free)
        with plan_lock:
            image.update(loaded)
            image["status"] = "loaded"
            save(output / "image-inventory.json", plan)
        receipt_path = output / "preflight" / (image["instance_id"] + ".json")
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_bytes())
            if (receipt["image_id"] != image["image_id"]
                    or receipt["base_commit"] != image["base_commit"]
                    or receipt["repo"] != image["repo"]
                    or receipt["preflight_policy_sha256"]
                    != hashlib.sha256(PREFLIGHT.encode()).hexdigest()):
                raise ValueError("preflight receipt image differs")
        else:
            receipt = preflight(image, output)
        with plan_lock:
            image["preflight_status"] = receipt["status"]
            image["environment_ready"] = receipt["status"] == "bounded_preflight_passed"
            plan["loaded_count"] = sum(row["status"] == "loaded" for row in plan["images"])
            plan["bounded_preflight_passed_count"] = sum(
                row.get("environment_ready", False) for row in plan["images"])
            save(output / "image-inventory.json", plan)

    def queue_ready():
        for job in load_jobs:
            if job.done():
                job.result()
        for image in plan["images"]:
            identity = image["instance_id"]
            if identity in queued:
                continue
            if all(item["digest"] in proofs for item in [image["config"], *image["layers"]]):
                queued.add(identity)
                load_jobs.append(loader.submit(finish_image, image))

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # Stable first-use task order makes whole images ready earlier than
            # fetching every tiny config before any repository layer.
            futures = [pool.submit(fetch, pair) for pair in plan["blobs"].items()]
            try:
                for future in as_completed(futures):
                    digest, proof = future.result()
                    proofs[digest] = proof
                    save(proof_path, proofs)
                    queue_ready()
            except Exception as error:
                stopped.set()
                range_pool.stop.set()
                cause = error.__cause__
                headers = getattr(cause, "headers", {})
                with plan_lock:
                    plan.update(
                        status="pausing_public_fault", error_type=type(error).__name__,
                        error=str(error)[:500], http_status=getattr(cause, "code", None),
                        retry_after=headers.get("Retry-After"), paused_at_utc=now())
                    save(output / "image-inventory.json", plan)
                for future in futures:
                    future.cancel()
                raise
        waiting_since = time.monotonic()
        while len(queued) != len(plan["images"]):
            queue_ready()
            if time.monotonic() - waiting_since > 1800:
                raise RuntimeError("existing_first_image_control_did_not_finish")
            time.sleep(1)
        for job in load_jobs:
            job.result()
    finally:
        stopped.set()
        for job in load_jobs:
            job.cancel()
        loader.shutdown(wait=True, cancel_futures=True)
        range_pool.close()
    plan["status"] = "image_preparation_complete"
    plan["loaded_count"] = sum(row["status"] == "loaded" for row in plan["images"])
    plan["bounded_preflight_passed_count"] = sum(row["environment_ready"] for row in plan["images"])
    plan["complete_environment_ready"] = False
    plan["remaining_environment_gate"] = "Independent official scorer and actual actor isolation integration."
    plan["completed_at_utc"] = now()
    save(output / "image-inventory.json", plan)


def load_ready_only(plan, output, *, minimum_free):
    """Load only complete verified local inputs, with no registry requests."""
    plan["daemon"] = daemon_identity()
    plan["status"] = "loading_verified_local_assets_only"
    plan["network_requests"] = 0
    proofs = dict(plan["reused_blob_proofs"])
    for digest, blob in plan["blobs"].items():
        if digest not in proofs:
            proof = cached_blob_proof(blob)
            if proof is not None:
                proofs[digest] = proof
    save(output / "blob-proofs.json", proofs)
    for image in plan["images"]:
        if not all(item["digest"] in proofs for item in [image["config"], *image["layers"]]):
            continue
        image.update(stream_load(image, plan["blobs"], proofs, output, minimum_free))
        image["status"] = "loaded"
        save(output / "image-inventory.json", plan)
        receipt_path = output / "preflight" / (image["instance_id"] + ".json")
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_bytes())
            if (receipt["image_id"] != image["image_id"]
                    or receipt["base_commit"] != image["base_commit"]
                    or receipt.get("preflight_policy_sha256")
                    != hashlib.sha256(PREFLIGHT.encode()).hexdigest()):
                raise ValueError("Existing local preflight identity differs")
        else:
            receipt = preflight(image, output)
        image["preflight_status"] = receipt["status"]
        image["environment_ready"] = receipt["status"] == "bounded_preflight_passed"
        save(output / "image-inventory.json", plan)
    plan["loaded_count"] = sum(row["status"] == "loaded" for row in plan["images"])
    plan["bounded_preflight_passed_count"] = sum(row["environment_ready"] for row in plan["images"])
    plan["complete_environment_ready"] = False
    plan["status"] = "assets_incomplete" if plan["loaded_count"] != 500 else "images_loaded"
    save(output / "image-inventory.json", plan)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--mirror-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--load-ready-only", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cdn-workers", type=int, default=16)
    parser.add_argument("--minimum-free-gib", type=int, default=200)
    args = parser.parse_args(argv)
    if args.execute and args.load_ready_only:
        parser.error("select either downloading or verified-local-only loading")
    if (not 1 <= args.workers <= 8 or not 1 <= args.cdn_workers <= 32
            or args.minimum_free_gib < 100):
        parser.error("workers must be 1..8 and disk reserve at least 100 GiB")
    args.output = args.output.resolve()
    if ROOT not in args.output.parents or not str(args.output).startswith("/data0/"):
        parser.error("preparation output must be on project /data0")
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / "blobs"
    cache.mkdir(exist_ok=True)
    plan = make_plan(args.inventory, args.official_root, args.mirror_summary, cache)
    save(args.output / ("plan-" + str(time.time_ns()) + ".json"), plan)
    if args.execute or args.load_ready_only:
        with (args.output / "preparation.lock").open("a+b") as process_lock:
            fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            prior_path = args.output / "image-inventory.json"
            if prior_path.exists():
                save(args.output / ("prior-state-" + str(time.time_ns()) + ".json"),
                     json.loads(prior_path.read_bytes()))
            try:
                if args.load_ready_only:
                    load_ready_only(plan, args.output, minimum_free=args.minimum_free_gib * GiB)
                else:
                    execute(plan, args.output, workers=args.workers,
                            minimum_free=args.minimum_free_gib * GiB, cdn_workers=args.cdn_workers)
            except Exception as error:
                plan.update(status="paused", error_type=type(error).__name__,
                            error=str(error)[:500], paused_at_utc=now())
                save(args.output / "image-inventory.json", plan)
                raise
    print(json.dumps({key: value for key, value in plan.items()
                      if key not in ("images", "blobs", "reused_blob_proofs")}))


if __name__ == "__main__":
    main()

"""Versioned, local-only official-image to shared Actor baseline preparation.

The grader's official image remains unchanged. Every admitted derived image
has the same tracked tree as its official setup HEAD and one new root commit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verified_image_prepare_v054 import (  # noqa: E402
    DOCKER, SOCKET, daemon_identity, disk_gate, docker, now, save,
)

POLICY_PATH = ROOT / "config/v054-actor-baseline-r2.json"
OUTPUT = ROOT / "runs/software-benchmark-v054/images/actor-admission-r2"
SOURCE = ROOT / "runs/software-benchmark-v054/images/preparation-r1/image-inventory.json"

# This program executes in the private, network-disabled preparation container.
# It receives only task/repository identities and the public policy, no gold,
# test patch, eval script, problem selection hint, or scorer feedback.
CONTAINER_PROGRAM = r'''
import glob, hashlib, json, os, shutil, subprocess, sys
task, policy = json.loads(sys.argv[1]), json.loads(sys.argv[2])
base, repo = task['base_commit'], task['repo']
def command(args, data=None, check=True, env=None):
    p = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and p.returncode:
        raise RuntimeError('Command failed: '+repr(args[:4])+': '+p.stderr.decode('utf-8','replace')[-2000:])
    return p
def git(*args, **kwargs):
    return command(['git','-c','safe.directory=/testbed','-C','/testbed']+list(args), **kwargs)
def text(p):
    return p.stdout.decode().strip()
def remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)
def in_checkout(path):
    real=os.path.realpath(path)
    return real == '/testbed' or real.startswith('/testbed/')

if not os.path.isdir('/testbed/.git') or os.path.islink('/testbed/.git'):
    raise RuntimeError('Expected a contained official Git object database')
official_head=text(git('rev-parse','HEAD'))
official_tree=text(git('rev-parse','HEAD^{tree}'))
base_tree=text(git('rev-parse',base+'^{tree}'))
if text(git('status','--porcelain')):
    raise RuntimeError('Official setup checkout is not clean')
commit=text(git('show','-s','--format=%P%n%an%n%ae%n%s','HEAD')).splitlines()
if official_head != base:
    if commit != [base, 'SWE-bench', 'setup@swebench.com', 'SWE-bench']:
        raise RuntimeError('Unrecognized official setup commit relationship: '+repr(commit))
raw=git('diff','--raw','--no-abbrev',base,'HEAD').stdout.decode().splitlines()
content_changes=[]
mode_changes=0
for line in raw:
    fields,path=line.split('\t',1)
    oldmode,newmode,oldblob,newblob,status=fields.split()
    if oldmode[1:] != newmode:
        mode_changes+=1
    if oldblob != newblob:
        content_changes.append(path)
tracked=git('ls-files','-z').stdout
ignored_before=git('ls-files','--others','--ignored','--exclude-standard','-z').stdout
targets=policy['targets'][repo]
copies=[]
source_paths={}
for name in targets['modules']:
    found=[('/testbed/'+template.format(name=name)) for template in policy['source_module_locations']
           if os.path.exists('/testbed/'+template.format(name=name))]
    if not found:
        raise RuntimeError('Public source module not found: '+name)
    source_paths[name]=found[0]
prefixes=['/opt/miniconda3','/opt/conda','/root/miniconda3']
for prefix in prefixes:
    distribution=targets['distribution']
    aliases=set([distribution,distribution.replace('-','_'),distribution.lower()])
    for alias in aliases:
        for path in sorted(glob.glob(prefix+'/pkgs/'+alias+'-[0-9]*')):
            if in_checkout(path):
                raise RuntimeError('Cache path unexpectedly resolves into checkout')
            copies.append({'path':path,'action':'remove_target_conda_cache'})
            remove(path)
    for name in targets['modules']:
        for pattern in (prefix+'/lib/python*/site-packages/'+name,
                        prefix+'/lib/python*/site-packages/'+name+'.py',
                        prefix+'/envs/*/lib/python*/site-packages/'+name,
                        prefix+'/envs/*/lib/python*/site-packages/'+name+'.py'):
            for path in sorted(glob.glob(pattern)):
                if in_checkout(path):
                    continue
                remove(path)
                os.symlink(source_paths[name],path)
                copies.append({'path':path,'action':'replace_target_copy_with_public_source_symlink',
                               'target':source_paths[name]})

# No original Git object, index, config, reflog or hook survives into Actor view.
shutil.rmtree('/testbed/.git')
git('init','--quiet')
git('config','core.filemode','true')
git('config','core.logallrefupdates','false')
git('update-index','--add','-z','--stdin',data=tracked)
actor_tree=text(git('write-tree'))
if actor_tree != official_tree:
    raise RuntimeError('Actor tracked tree differs from official setup tree')
identity=policy['new_git_identity']
env=dict(os.environ)
env.update(GIT_AUTHOR_NAME=identity['name'],GIT_AUTHOR_EMAIL=identity['email'],
           GIT_COMMITTER_NAME=identity['name'],GIT_COMMITTER_EMAIL=identity['email'],
           GIT_AUTHOR_DATE=identity['date'],GIT_COMMITTER_DATE=identity['date'])
actor_head=text(git('commit-tree',actor_tree,data=(identity['message']+'\n').encode(),env=env))
git('symbolic-ref','HEAD','refs/heads/v054-baseline')
git('update-ref','refs/heads/v054-baseline',actor_head)
clean=not text(git('status','--porcelain'))
fsck=git('fsck','--full','--strict','--no-reflogs','--unreachable',check=False)
objects=git('cat-file','--batch-all-objects','--batch-check=%(objecttype)').stdout.splitlines()
commit_count=objects.count(b'commit')
old_head_unavailable=git('cat-file','-e',official_head,check=False).returncode != 0
original_base_unavailable=git('cat-file','-e',base,check=False).returncode != 0
ignored_after=git('ls-files','--others','--ignored','--exclude-standard','-z').stdout
if (not clean or fsck.returncode or fsck.stdout or fsck.stderr or commit_count != 1
        or not old_head_unavailable or not original_base_unavailable
        or ignored_after != ignored_before):
    raise RuntimeError('Reconstructed Git isolation or preserved public build artifacts failed')
remaining=[]
for action in copies:
    path=action['path']
    if action['action']=='remove_target_conda_cache' and os.path.lexists(path):
        remaining.append(path)
    elif action['action'].startswith('replace') and not in_checkout(path):
        remaining.append(path)
if remaining:
    raise RuntimeError('Target package copy remains: '+repr(remaining))
python=next((p for p in ['/opt/miniconda3/envs/testbed/bin/python',
                       '/opt/conda/envs/testbed/bin/python'] if os.access(p,os.X_OK)),None)
if python is None:
    raise RuntimeError('No explicit official testbed Python')
probe=command([python,'-c','import json,sys;print(json.dumps({"executable":sys.executable,"version":sys.version,"prefix":sys.prefix}))'])
python_details=json.loads(probe.stdout)
print(json.dumps({'official_head':official_head,'official_tree':official_tree,'base_tree':base_tree,
  'official_setup_commit':{'parents':commit[0].split(),'author':commit[1:3],'subject':commit[3]},
  'setup_changed_path_count':len(raw),'setup_mode_changed_count':mode_changes,
  'setup_content_changed_paths':content_changes,'actor_head':actor_head,'actor_tree':actor_tree,
  'actor_tree_equals_official_tree':actor_tree==official_tree,'working_tree_clean':clean,
  'old_git_object_database_removed':True,'old_head_unavailable':old_head_unavailable,
  'dataset_base_object_unavailable':original_base_unavailable,'git_commit_object_count':commit_count,
  'git_fsck_returncode':fsck.returncode,'git_fsck_stdout':fsck.stdout.decode(),
  'git_fsck_stderr':fsck.stderr.decode(),'target_copy_actions':copies,
  'target_package_copy_paths':remaining,'ignored_build_artifact_count':len(ignored_after.split(b'\0'))-1,
  'public_python':python,'public_python_details':python_details,'preparation_uid':os.getuid(),
  'preparation_gid':os.getgid(),'source_module_paths':source_paths}))
'''


def policy_identity():
    policy = json.loads(POLICY_PATH.read_bytes())
    return policy, hashlib.sha256(
        POLICY_PATH.read_bytes() + b"\0" + CONTAINER_PROGRAM.encode()).hexdigest()


def config_blob(image_id):
    digest = image_id.removeprefix("sha256:")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Invalid derived image config digest")
    destination = OUTPUT / "configs" / (digest + ".json")
    if not destination.exists():
        source = ROOT / "runs/software-panel-v053/docker/data/image/overlay2/imagedb/content/sha256" / digest
        # Only read this private daemon's immutable config; never write its store.
        result = subprocess.run(["sudo", "-n", "cat", str(source)],
                                capture_output=True, check=True)
        if hashlib.sha256(result.stdout).hexdigest() != digest:
            raise ValueError("Derived Docker config bytes differ from image ID")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(result.stdout)
    return str(destination)


def prepare(row, policy, policy_sha, retry_technical_unknown=False):
    destination = OUTPUT / "instances" / (row["instance_id"] + ".json")
    if destination.exists():
        prior = json.loads(destination.read_bytes())
        if (prior["policy_sha256"] != policy_sha
                or prior["official_image_id"] != row["config_digest"]):
            raise ValueError("Existing actor preparation belongs to a different policy/image")
        if prior["status"] == "technical_unknown" and retry_technical_unknown:
            history = OUTPUT / "prior-attempts" / row["instance_id"] / (str(time.time_ns()) + ".json")
            history.parent.mkdir(parents=True, exist_ok=True)
            destination.rename(history)
        elif prior["status"] == "actor_baseline_admitted" and not prior.get("actor_config_blob"):
            prior["actor_config_blob"] = config_blob(prior["actor_image_id"])
            save(destination, prior)
            return prior
        else:
            return prior
    disk_gate(OUTPUT, 200 * 1024 ** 3)
    receipt = {
        "schema": "proworksim.v054.actor-admission-r2", "instance_id": row["instance_id"],
        "repo": row["repo"], "dataset_base": row["base_commit"],
        "official_image_id": row["config_digest"],
        "official_image_name": row["image_name"] + ":" + row["tag"],
        "official_manifest_digest": row["manifest_digest"],
        "policy_sha256": policy_sha, "started_at_utc": now(),
        "conditions": policy["conditions"], "network": "none",
        "official_grading_image_modified": False, "hidden_material_loaded": False,
        "model_calls": 0, "test_executions": 0,
    }
    name = "pws-v054-baseline-r2-" + hashlib.sha256(row["instance_id"].encode()).hexdigest()[:16]
    container = None
    try:
        inspected = json.loads(docker("image", "inspect", row["config_digest"]).stdout)[0]
        if (inspected["Id"] != row["config_digest"] or inspected["Os"] != "linux"
                or inspected["Architecture"] != "amd64"):
            raise ValueError("Wrong original image identity or platform")
        created = docker(
            "create", "--pull", "never", "--name", name, "--network", "none",
            "--label", "proworksim.v054.baseline=" + row["instance_id"],
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--cpus", "4", "--memory", str(16 * 1024 ** 3), "--pids-limit", "4096",
            "--user", "0:0", "--workdir", "/testbed", "--entrypoint", "/bin/bash",
            row["config_digest"], "-c", "exec sleep infinity")
        container = created.stdout.strip()
        docker("start", container)
        task = {"base_commit": row["base_commit"], "repo": row["repo"]}
        process = subprocess.run(
            [DOCKER, "--host", SOCKET, "exec", "-i", container,
             "/usr/bin/python3", "-I", "-", json.dumps(task), json.dumps(policy)],
            input=CONTAINER_PROGRAM, capture_output=True, text=True, timeout=600)
        if process.returncode:
            raise RuntimeError("Actor construction failed: " + process.stderr[-4000:])
        details = json.loads(process.stdout)
        receipt.update(details)
        tag = "proworksim/v054-actor-r2:" + row["instance_id"].replace("__", "_")
        committed = docker(
            "commit", "--change", "LABEL proworksim.baseline.policy=" + policy_sha,
            container, tag, timeout=600)
        actor_id = committed.stdout.strip().splitlines()[-1]
        derived = json.loads(docker("image", "inspect", actor_id).stdout)[0]
        if derived["Id"] != actor_id or derived["Os"] != "linux" or derived["Architecture"] != "amd64":
            raise ValueError("Derived actor image identity/platform mismatch")
        receipt.update(status="actor_baseline_admitted", actor_image_id=actor_id,
                       actor_image_name=tag, actor_config_digest=actor_id,
                       actor_config_blob=config_blob(actor_id),
                       platform={"os": "linux", "architecture": "amd64"},
                       completed_at_utc=now())
    except Exception as error:
        receipt.update(status="technical_unknown", error_type=type(error).__name__,
                       error=str(error)[:4500], completed_at_utc=now())
        if isinstance(error, subprocess.CalledProcessError):
            receipt["command_stderr"] = str(error.stderr or "")[-4000:]
    finally:
        if container:
            docker("rm", "--force", container, check=False)
    save(destination, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", action="append")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retry-technical-unknown", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("one through eight preparation containers only")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "controller.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = json.loads(SOURCE.read_bytes())
        if len(plan["images"]) != 500:
            raise ValueError("All 500 planned identities must be preserved")
        policy, policy_sha = policy_identity()
        selected = [row for row in plan["images"] if not args.instance or row["instance_id"] in args.instance]
        if args.instance and len(selected) != len(set(args.instance)):
            raise ValueError("Selected identity absent from fixed full inventory")
        state = {
            "schema": "proworksim.v054.actor-admission-batch-r2", "status": "preparing",
            "started_at_utc": now(), "policy_sha256": policy_sha,
            "inventory_sha256": plan["inventory_sha256"], "planned_instances": 500,
            "selected_instances": len(selected), "workers": args.workers,
            "daemon": daemon_identity(), "model_calls": 0, "network_requests": 0,
            "results": {},
        }
        save(OUTPUT / "state.json", state)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = {}
            waiting = {row["instance_id"]: row for row in selected}
            while waiting or pending:
                current = json.loads(SOURCE.read_bytes())
                loaded = {row["instance_id"] for row in current["images"] if row.get("status") == "loaded"}
                for identity in list(waiting):
                    if identity in loaded:
                        row = waiting.pop(identity)
                        pending[pool.submit(prepare, row, policy, policy_sha,
                                            args.retry_technical_unknown)] = identity
                completed = [future for future in pending if future.done()]
                if not completed and pending:
                    completed = [next(as_completed(pending))]
                for future in completed:
                    identity = pending.pop(future)
                    result = future.result()
                    state["results"][identity] = {
                        "status": result["status"], "actor_image_id": result.get("actor_image_id"),
                        "error": result.get("error"),
                    }
                state["admitted_count"] = sum(row["status"] == "actor_baseline_admitted"
                                               for row in state["results"].values())
                state["technical_unknown_count"] = sum(row["status"] == "technical_unknown"
                                                        for row in state["results"].values())
                state["waiting_for_offline_load"] = len(waiting)
                save(OUTPUT / "state.json", state)
                if waiting and not pending:
                    time.sleep(5)
        state.update(completed_at_utc=now(), status=("all_selected_admitted"
                     if state["admitted_count"] == len(selected) else "closed_with_technical_unknown"))
        save(OUTPUT / "state.json", state)
        print(json.dumps({key: value for key, value in state.items() if key != "results"}))


if __name__ == "__main__":
    main()

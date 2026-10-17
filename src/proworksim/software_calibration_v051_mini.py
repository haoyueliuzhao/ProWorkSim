"""Pinned mini-SWE DefaultAgent loop with raw Qwen/native shell bridges.

This module never loads a model. The host supplies one already-admitted raw
project-path CalibrationActor and one fresh buggy-only repository worktree.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from types import SimpleNamespace

from proworksim.candidate_runtime_v017 import parse_candidate_generated
from proworksim.deterministic_work_v024 import deterministic_tool_ids
from proworksim.software_calibration_runtime_v051 import prepare_native_input
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "software-calibration-mini-bridge-v0.51"
MINI_COMMIT = "a83fcae82d2a08f0ee0c688f9d137b3566c097f8"
PUBLIC_TEST_COMMAND = "calibration_public_tests"
EXPECTED = {"context_limit": 18432, "max_output_tokens": 2048, "enable_thinking": False,
            "preserve_thinking": False, "temperature": .7, "top_p": 1., "top_k": 0,
            "max_generation_seconds": 600}


def bind_mini(manifest, config_dir):
    manifest = Path(manifest).resolve()
    value = read_json(manifest)
    if value.get("git_ref") != MINI_COMMIT or value.get("package_version") != "2.4.6":
        raise ValueError("Only the predeclared mini-SWE 2.4.6 source is admitted")
    package = None
    for row in value["files"]:
        path = Path(row["local_path"])
        raw = path.read_bytes()
        if (hashlib.sha256(raw).hexdigest() != row["sha256"]
                or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != row["git_blob_sha1"]):
            raise ValueError("Pinned mini source changed: " + row["upstream_path"])
        if row["upstream_path"] == "src/minisweagent/__init__.py":
            package = path.parent.parent
    if package is None:
        raise ValueError("Pinned mini package root missing")
    config_dir = Path(config_dir).resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    if (config_dir / ".env").exists():
        raise ValueError("A calibration must not import a user global mini configuration")
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(config_dir)
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    sys.path.insert(0, str(package))
    import minisweagent
    from minisweagent.agents.default import DefaultAgent
    import yaml
    if Path(minisweagent.__file__).resolve() != package / "minisweagent/__init__.py":
        raise ValueError("Another mini installation was imported")
    config = yaml.safe_load((package / "minisweagent/config/mini.yaml").read_text())
    return DefaultAgent, config, {"version": "2.4.6", "git_ref": MINI_COMMIT,
        "manifest_sha256": digest(manifest.read_bytes()), "package_path": str(package),
        "DefaultAgent_loop_modified": False, "vendor_end_to_end_reproduction": False}


def _safe_relative(name):
    return (isinstance(name, str) and name and not Path(name).is_absolute()
            and ".." not in Path(name).parts and ".git" not in Path(name).parts)


def prepare_buggy_worktree(files, destination, *, receipt_path):
    """Only buggy source enters the new single-commit history; never clone."""
    destination = Path(destination).resolve()
    if (destination.exists() or not files or any(not _safe_relative(k) or not isinstance(v, str)
            for k, v in files.items())):
        raise ValueError("A fresh worktree and exact UTF-8 buggy file mapping are required")
    destination.mkdir(parents=True)
    for name, text in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "v051 calibration",
        "GIT_AUTHOR_EMAIL": "calibration@local.invalid", "GIT_COMMITTER_NAME": "v051 calibration",
        "GIT_COMMITTER_EMAIL": "calibration@local.invalid",
        "GIT_AUTHOR_DATE": "2026-10-17T00:00:00+00:00", "GIT_COMMITTER_DATE": "2026-10-17T00:00:00+00:00"}

    def git(*args):
        result = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=destination, env=env, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError("Fresh buggy-only repository setup failed: " + result.stderr)
        return result.stdout.strip()

    git("init", "--quiet")
    git("add", "--all", "--force")
    git("commit", "--quiet", "--no-verify", "-m", "Frozen buggy calibration initial tree")
    receipt = {"version": VERSION, "worktree": str(destination), "initial_files_sha256": digest(json_bytes(files)),
        "initial_commit": git("rev-parse", "HEAD"), "commit_count": int(git("rev-list", "--all", "--count")),
        "remotes": git("remote", "-v"), "correct_reference_files_imported": False,
        "upstream_history_imported": False, "source_mode": "fresh buggy-only single commit"}
    if receipt["commit_count"] != 1 or receipt["remotes"]:
        raise ValueError("The native initial repository must contain no upstream history or remote")
    atomic_write(Path(receipt_path), json_bytes(receipt))
    return receipt


def read_worktree(worktree):
    root = Path(worktree).resolve()
    files = {}
    for parent, directories, names in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name not in {".git", ".calibration-tmp", ".pytest_cache", "__pycache__"}]
        for name in directories:
            if (Path(parent) / name).is_symlink():
                raise ValueError("Native deliverable contains an unsupported directory symlink")
        for name in names:
            path = Path(parent) / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Native deliverable must contain ordinary UTF-8 files")
            key = str(path.relative_to(root))
            files[key] = path.read_text(encoding="utf-8")
    if len(files) > 5000 or sum(len(value.encode()) for value in files.values()) > 33554432:
        raise ValueError("Native source snapshot exceeds the predeclared finite tree budget")
    return files


def fixed_patch(initial, final):
    pieces = []
    for name in sorted(set(initial) | set(final)):
        if initial.get(name) == final.get(name):
            continue
        pieces.extend(difflib.unified_diff(initial.get(name, "").splitlines(keepends=True),
            final.get(name, "").splitlines(keepends=True),
            fromfile="a/" + name if name in initial else "/dev/null",
            tofile="b/" + name if name in final else "/dev/null"))
    return "".join(pieces)


def production_domain(task):
    if task["module"] == "boltons":
        location = "new .py helper modules under boltons/"
    elif task["module"] in {"parse", "xmltodict"}:
        location = "new top-level .py helper modules"
    else:
        raise ValueError("Declare the production domain of one frozen CAL2 repository")
    return ("Final evaluation retains edits/deletions of the declared original production files and " + location
        + ". Original tests/configuration/support are restored by the evaluator; changes to them remain in "
        "your raw workspace record but cannot alter the oracle. New conftest.py and pytest/build configuration "
        "files are excluded from the evaluation tree. Keep task implementation inside the declared production domain.")


class NativeModel:
    def __init__(self, owner, *, output, config, started_at, episode_binding, token_limit=500000, decision_limit=128):
        if token_limit != 500000 or decision_limit != 128:
            raise ValueError("Retain the one frozen 500k-token/128-query CAL2 inventory budget")
        if owner.path != "project" or owner.freeze_identity().get("raw_release") is not True:
            raise ValueError("R is the raw original release using the same project numerical provider as P/U")
        if any(owner.contract.get(key) != value for key, value in EXPECTED.items()):
            raise ValueError("R requires the frozen shared CAL2 research decoder, not the CAL1 profile")
        self.owner, self.output, self.config = owner, Path(output), copy.deepcopy(config)
        self.episode_binding = copy.deepcopy(episode_binding)
        self.started_at, self.token_limit, self.decision_limit = started_at, token_limit, decision_limit
        self.decisions = self.attempts = self.actual_tokens = self.complete_responses = 0
        self.inflight = None
        self.stop_reason = None
        self.stop_receipt = None
        self.preexecution_rejections = []
        self.calls = []
        self.output.mkdir(parents=True, exist_ok=False)
        self._save()

    def _save(self):
        atomic_write(self.output / "ledger.json", json_bytes(self.snapshot()))

    def snapshot(self):
        return {"version": VERSION, "decisions": self.decisions, "attempts": self.attempts,
            "complete_responses": self.complete_responses, "known_actual_tokens": self.actual_tokens,
            "inflight": self.inflight, "reserved_unknown_tokens": self.inflight["reservation"] if self.inflight else 0,
            "token_limit": self.token_limit, "decision_limit": self.decision_limit,
            "stop_reason": self.stop_reason, "calls": copy.deepcopy(self.calls),
            "stop_receipt": copy.deepcopy(self.stop_receipt),
            "episode_binding": copy.deepcopy(self.episode_binding),
            "preexecution_rejections": copy.deepcopy(self.preexecution_rejections),
            "automatic_model_retries": False, "local_dollar_cost_estimate": None}

    def _stop(self, status, reason):
        from minisweagent.exceptions import LimitsExceeded
        self.stop_reason = reason
        self.stop_receipt = {"status": status, "reason": reason, "elapsed_seconds": time.monotonic() - self.started_at,
            "decisions": self.decisions, "attempts": self.attempts, "actual_tokens": self.actual_tokens,
            "generation_started": False, "new_world_side_effect": False,
            "actor_identity": self.owner.freeze_identity(), "episode_binding": copy.deepcopy(self.episode_binding)}
        self._save()
        raise LimitsExceeded({"role": "exit", "content": status,
            "extra": {"exit_status": status, "submission": "", "calibration_reason": reason}})

    def _reject_preexecution(self, native, *, reason):
        receipt = {"version": VERSION, "reason": reason, "native_input": copy.deepcopy(native),
            "P": native["prompt_tokens"], "O": self.owner.contract["max_output_tokens"],
            "C": self.owner.contract["context_limit"], "fits": native["fits"],
            "remaining_tokens": self.token_limit - self.actual_tokens,
            "decisions": self.decisions, "attempts": self.attempts, "actual_tokens": self.actual_tokens,
            "generation_started": False, "new_side_effect": False, "side_effect_scope": "model/world operations",
            "actor_identity": self.owner.freeze_identity(), "episode_binding": copy.deepcopy(self.episode_binding)}
        path = self.output / (f"preexecution-rejection-{self.decisions:03d}.json")
        atomic_write(path, json_bytes(receipt))
        self.preexecution_rejections.append({"path": str(path.resolve()), "sha256": digest(path.read_bytes())})

    def query(self, messages, **kwargs):
        from minisweagent.exceptions import FormatError
        from minisweagent.models.utils.actions_toolcall import BASH_TOOL, parse_toolcall_actions
        if kwargs:
            raise ValueError("No per-call decoder overrides in the frozen native model")
        if self.decisions >= self.decision_limit:
            self._stop("LimitsExceeded", "decision_limit")
        if time.monotonic() - self.started_at >= 5400:
            self._stop("TimeExceeded", "administrative_soft_deadline")
        self.decisions += 1
        request = {"model": "raw-qwen3.5-9b-v051", "temperature": self.owner.contract["temperature"],
            "max_tokens": self.owner.contract["max_output_tokens"], "tools": [BASH_TOOL],
            "messages": [{key: copy.deepcopy(value) for key, value in message.items() if key != "extra"}
                         for message in messages]}
        native = prepare_native_input(self.owner.tokenizer, request, self.owner.contract)
        if not native["fits"]:
            self._reject_preexecution(native, reason="full_native_context_preexecution_rejection")
            self._stop("ContextWindowExceeded", "full_native_context_preexecution_rejection")
        reservation = native["prompt_tokens"] + self.owner.contract["max_output_tokens"]
        if reservation > self.token_limit - self.actual_tokens:
            self._reject_preexecution(native, reason="full_request_token_reservation_insufficient")
            self._stop("TokenBudgetExhausted", "full_request_token_reservation_insufficient")
        self.attempts += 1
        self.inflight = {"attempt": self.attempts, "reservation": reservation,
            "native_input_sha256": native["sha256"], "started_at": time.time()}
        self._save()
        # Exactly one provider call. Faults retain the uncompleted reservation.
        result = self.owner.generate_native(native)
        usage = result["usage"]
        if (any(type(usage.get(key)) is not int for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != native["prompt_tokens"]
                or usage["completion_tokens"] != len(result["output_ids"])
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                or not 0 < usage["total_tokens"] <= reservation):
            raise RuntimeError("Native actual usage cannot settle its prepared request")
        self.actual_tokens += usage["total_tokens"]
        self.complete_responses += 1
        self.inflight = None
        self.calls.append({"attempt": self.attempts, "native_attempt_id": result.get("attempt_id"),
            "usage": copy.deepcopy(usage), "finish_reason": result["finish_reason"],
            "native_input_sha256": native["sha256"]})
        atomic_write(self.output / (f"response-{self.attempts:03d}.json"), json_bytes(result))
        self._save()
        message, parse_error = parse_candidate_generated(result["raw_generated_text"], request)
        message = deterministic_tool_ids(message, request, result["raw_generated_text"])
        tools = message.get("tool_calls") or []
        try:
            if parse_error or len(tools) != 1:
                raise FormatError({"role": "user", "content":
                    "This frozen interface requires exactly one complete native bash tool call per response. "
                    "Use bash with one string command; the command may combine shell operations.",
                    "extra": {"interrupt_type": "FormatError", "parse_error": parse_error,
                              "observed_tool_calls": len(tools)}})
            objects = [SimpleNamespace(id=call["id"], function=SimpleNamespace(**call["function"])) for call in tools]
            actions = parse_toolcall_actions(objects, format_error_template=self.config["format_error_template"],
                template_kwargs={"finish_reason": result["finish_reason"]})
            if not isinstance(actions[0]["command"], str) or not actions[0]["command"].strip():
                raise FormatError({"role": "user", "content": "bash.command must be a nonempty string.",
                                   "extra": {"interrupt_type": "FormatError"}})
        except FormatError as error:
            error.messages[0].setdefault("extra", {}).update(cost=0.0, actual_tokens=usage["total_tokens"],
                response=result, original_assistant_message=message)
            raise
        message["extra"] = {"actions": actions, "cost": 0.0, "actual_tokens": usage["total_tokens"],
            "native_attempt_id": result.get("attempt_id"), "timestamp": time.time()}
        return message

    def format_message(self, **kwargs):
        return copy.deepcopy(kwargs)

    def format_observation_messages(self, message, outputs, template_vars=None):
        from minisweagent.models.utils.actions_toolcall import format_toolcall_observation_messages
        return format_toolcall_observation_messages(actions=message["extra"]["actions"], outputs=outputs,
            observation_template=self.config["observation_template"], template_vars=template_vars)

    def get_template_vars(self, **kwargs):
        return {**copy.deepcopy(self.config), **kwargs}

    def serialize(self):
        return {"info": {"config": {"model_type": VERSION, "model": self.get_template_vars()},
                          "calibration_ledger": self.snapshot()}}


class NativeEnvironment:
    def __init__(self, *, worktree, task, output, started_at):
        self.worktree, self.task, self.output = Path(worktree).resolve(), copy.deepcopy(task), Path(output)
        self.started_at, self.actions, self.public_tests = started_at, 0, 0
        self.output.mkdir(parents=True, exist_ok=False)

    def execute(self, action, cwd=""):
        from minisweagent.environments.local import LocalEnvironment
        from proworksim.software_calibration_shell_v051 import run_bounded_shell
        from proworksim.software_calibration_repo_tests_v051 import run_repository_tests
        if cwd and Path(cwd).resolve() != self.worktree:
            raise ValueError("Only the declared native worktree is an execution root")
        if self.actions >= 128 or time.monotonic() - self.started_at >= 6000:
            raise RuntimeError("Native action/hard episode guard exceeded")
        self.actions += 1
        command = action.get("command")
        if command == PUBLIC_TEST_COMMAND:
            self.public_tests += 1
            result = run_repository_tests(files=read_worktree(self.worktree), task=self.task,
                run_root=self.output / (f"public-tests-{self.public_tests:03d}"))
            output = {"output": result["stdout"], "returncode": result["returncode"],
                "exception_info": "" if result["executed"] else "Frozen public test runner did not produce a complete trusted execution receipt.",
                "extra": {"public_test_call": self.public_tests, "test_evidence": result["evidence"],
                          "native_test_results": result["tests"], "source_unchanged": result["source_unchanged"]}}
        else:
            python = Path(self.task["cpu_python"]).absolute()
            output = run_bounded_shell(command, worktree=self.worktree, python_executable=python,
                python_prefix=python.parent.parent, evidence_root=self.output / "shell-calls", timeout_seconds=30)
        atomic_write(self.output / (f"action-{self.actions:03d}.json"), json_bytes({"action": action, "output": output}))
        # Retain the exact upstream completion-marker semantics.
        LocalEnvironment._check_finished(self, output)
        return output

    def get_template_vars(self, **kwargs):
        return {"cwd": str(self.worktree), **platform.uname()._asdict(), **kwargs}

    def serialize(self):
        return {"info": {"config": {"environment_type": VERSION,
            "environment": {"cwd": str(self.worktree), "public_tests_command": PUBLIC_TEST_COMMAND,
                "max_actions": 128, "public_test_count_cap": None, "command_timeout_seconds": 30,
                "public_tests_editable_in_native_workspace": True,
                "authoritative_tests_restored_by_host_for_final_grade": True}},
            "native_actions": self.actions, "native_public_test_calls": self.public_tests}}


def run_native_case(owner, *, task, worktree, seed, output, mini_manifest, workspace_receipt, initial_files):
    """Run one declared R episode. Host owns admission, grading and global stops."""
    output, worktree = Path(output).resolve(), Path(worktree).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if (workspace_receipt.get("worktree") != str(worktree)
            or workspace_receipt.get("initial_files_sha256") != digest(json_bytes(initial_files))
            or digest(json_bytes(read_worktree(worktree))) != workspace_receipt["initial_files_sha256"]
            or workspace_receipt.get("commit_count") != 1 or workspace_receipt.get("remotes")):
        raise ValueError("Native case lacks its exact fresh buggy-only initial worktree binding")
    DefaultAgent, config, mini_source = bind_mini(mini_manifest, output / "mini-global-config")
    started = time.monotonic()
    before = owner.capture_evaluation_state()
    owner.begin_window("v051-cal2-R:" + task["task_id"])
    owner.reseed(seed, label=task["task_id"] + "-R")
    model = NativeModel(owner, output=output / "model", config=config["model"], started_at=started,
        episode_binding={"task_id": task["task_id"], "condition": "R", "seed": seed,
                         "initial_files_sha256": workspace_receipt["initial_files_sha256"]})
    environment = NativeEnvironment(worktree=worktree, task=task, output=output / "environment", started_at=started)
    extension = (
        "\n\nFrozen calibration interface: issue exactly one native bash tool call per response. "
        "One bash command may combine shell operations. The complete original public test suite is available "
        "with the standalone command `calibration_public_tests`; do not combine that reserved command with "
        "other shell syntax. It uses the declared local TCP descriptor fixture. Other shell networking is disabled. "
        "There is no separate 32-test counter in this native condition; every test invocation consumes a real "
        "query/action from the common 128 limit. Retained delivery files must be ordinary UTF-8 files. "
        "Only this buggy initial commit is present; no upstream history or remote is available."
    ) + "\n" + production_domain(task)
    agent = DefaultAgent(model, environment, system_template=config["agent"]["system_template"],
        instance_template=config["agent"]["instance_template"] + extension,
        step_limit=128, cost_limit=0.0, wall_time_limit_seconds=5400,
        max_consecutive_format_errors=3, output_path=output / "trajectory.json")
    status = "execution_fault"
    terminal = None
    try:
        terminal = agent.run(task=task["problem_statement"])
        status = "bounded_native_episode_closed"
        final = read_worktree(worktree)
        atomic_write(output / "candidate-files.json", json_bytes(final))
        (output / "prediction.patch").write_text(fixed_patch(initial_files, final))
        report = {"version": VERSION, "status": status, "task_id": task["task_id"], "seed": seed,
            "mini_source": mini_source, "terminal": terminal,
            "native_submission_signal": terminal.get("exit_status") == "Submitted",
            "initial_files_sha256": workspace_receipt["initial_files_sha256"],
            "candidate_files_sha256": digest(json_bytes(final)), "candidate_files": str(output / "candidate-files.json"),
            "prediction_patch": str(output / "prediction.patch"), "ledger": model.snapshot(),
            "upstream_limit_receipt": {"terminal_status": terminal.get("exit_status"),
                "agent_query_count": agent.n_calls, "native_model_decisions": model.decisions,
                "elapsed_agent_seconds": time.time() - agent._start_time,
                "step_limit": 128, "wall_time_limit_seconds": 5400,
                "actual_inflight": copy.deepcopy(model.inflight),
                "origin": "Unmodified pinned DefaultAgent.query pre-dispatch limits"},
            "actions": environment.actions, "public_tests": environment.public_tests,
            "R_native_correctness": None, "project_delivery_requirement": "not_applicable_to_native_framework",
            "seconds": time.monotonic() - started, "new_model_qualifications": 0,
            "new_backward_calls": 0, "new_parameter_updates": 0,
            "framework_difference": "Original mini loop with one native bash call per query; no project 32-test cap or fixed-submit workflow. Code correctness scored separately by host from frozen tests."}
        atomic_write(output / "report.json", json_bytes(report))
        return report
    except BaseException as error:
        atomic_write(output / "interruption.json", json_bytes({"version": VERSION, "status": status,
            "error": {"type": type(error).__name__, "message": str(error)}, "ledger": model.snapshot(),
            "seconds": time.monotonic() - started, "automatic_retry_allowed": False}))
        raise
    finally:
        if owner.phase == "collecting" and not owner.busy:
            owner.finish_evaluation([], output / "evaluation-close")
        guard = owner.finish_evaluation_guard(before)
        atomic_write(output / "evaluation-guard.json", json_bytes(guard))
        if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
            raise RuntimeError("Native frozen actor/RNG evaluation guard failed")

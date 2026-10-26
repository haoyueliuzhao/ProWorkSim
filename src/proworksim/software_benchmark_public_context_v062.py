"""Public-only context and observation advice for the v062 FIX conditions.

This module performs no command execution. Callers retain the original isolated
native tool and its permissions. BASE does not use this module's interventions.
"""
from __future__ import annotations

import copy
import json
from pathlib import PurePosixPath
import re
import shlex

from .software_benchmark_candidates_v054 import checked, reference

VERSION = "v062-public-context-and-native-feedback-r1"
SELECTION = "repository-wide public default; no answer-derived files or task-result selection"
PROBE_MARKER = "PWS_V062_PUBLIC_PYTHON="
MULTI_COMMAND_PREFIX = (
    "Cannot execute multiple commands at once.\n"
    "Please run each command separately OR chain them into a single "
    "command via && or ;\nProvided commands:\n"
)
TERMINAL_GUIDANCE = """Public terminal usage:
- The terminal accepts one native shell command per call. Bare independent command lines can be rejected before execution. Submit separate calls, explicitly join dependent commands with &&, or deliberately author a script and invoke it. Multiline strings and heredocs are not automatically invalid; the native parser remains authoritative.
- If a command is still running, use the native continuation or interrupt operation before another command. No rejected command is automatically split, rewritten or retried."""
MULTI_COMMAND_GUIDANCE = (
    "[v062 public tool feedback] The native terminal rejected this action before "
    "executing its commands. Choose separate terminal calls, deliberately join "
    "dependent commands with &&, or write a script with file_editor and invoke "
    "that script. Do not blindly replace newlines: quoted text and heredocs can "
    "contain meaningful newlines. The original command was not rewritten or retried."
)


def _public_python(value):
    if (not isinstance(value, str) or not value.startswith("/")
            or re.fullmatch(r"/[A-Za-z0-9_./+\-]+", value) is None
            or ".." in PurePosixPath(value).parts
            or value.startswith(("/data0/", "/data1/", "/home/zhuxinrui/", "/pws/",
                                 "/opt/pws-runtime/", "/opt/pws-control/"))):
        raise ValueError("An admitted public image interpreter path is required")
    return value


def _environment(public):
    python = _public_python(public.get("public_python"))
    environment = public.get("environment")
    if (public.get("kind") != "official_image" or not isinstance(environment, dict)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", public.get("image_id", "")) is None
            or public.get("source_config_sha256") != public["image_id"].removeprefix("sha256:")):
        raise ValueError("The pinned original public image environment is required")
    for key in ("PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
        value = environment.get(key)
        if value is not None and (not isinstance(value, str) or any(c in value for c in "\0\r\n")
                or any(marker in value for marker in
                       ("/data0/", "/data1/", "/home/zhuxinrui", "/pws/",
                        "/opt/pws-runtime", "/opt/pws-control", "resident-venv"))):
            raise ValueError("Interpreter initialization may use only public image environment values")
    path = environment.get("PATH", "")
    if (not isinstance(path, str) or path.split(":")[0] != str(PurePosixPath(python).parent)
            or any(not component.startswith("/") or ".." in PurePosixPath(component).parts
                   for component in path.split(":"))):
        raise ValueError("Public PATH must select the admitted interpreter without relative entries")
    return python, environment


def repository_frontend(repo, python):
    """Repository-level rules from the original public frontend builder only."""
    python = _public_python(python)
    if repo == "django/django":
        return [python, "tests/runtests.py", "--noinput", "--parallel", "1"]
    if repo == "sympy/sympy":
        return [python, "bin/test"]
    return [python, "-m", "pytest"]


def prepare_public_context(public_task, *, registry_reference, baseline_mapping_reference,
                           public_environment):
    """Bind source identities, then project an explicit, minimal public allowlist.

    Registry extras, baseline mapping details and qualification output are never
    interpolated into model-visible text. Arbitrary task-selected argv additions
    are rejected even when the registry claims that their source is public.
    """
    registry = json.loads(checked(registry_reference).read_bytes())
    mapping = json.loads(checked(baseline_mapping_reference).read_bytes())
    python, _ = _environment(public_environment)
    entries = [entry for entry in registry.get("entries", [])
               if entry.get("instance_id") == public_task.get("instance_id")]
    if (registry.get("version") != "software-benchmark-public-test-registry-v054"
            or registry.get("planned_tasks") != 500 or len(entries) != 1):
        raise ValueError("One admitted entry in the frozen public registry is required")
    entry = entries[0]
    if (entry.get("admitted") is not True or entry.get("source") != "public_repository"
            or entry.get("hidden_material_used") is not False or entry.get("selection") != SELECTION
            or entry.get("cwd") != "/testbed" or entry.get("repo") != public_task.get("repo")
            or entry.get("baseline_mapping") != baseline_mapping_reference
            or mapping.get("instance_id") != public_task.get("instance_id")
            or mapping.get("repo") != public_task.get("repo")
            or mapping.get("dataset_base") != public_task.get("base_commit")
            or mapping.get("public_python") != python or entry.get("public_python") != python
            or mapping.get("actor_image_id") != public_environment["image_id"]):
        raise ValueError("Public context source, task, interpreter or actor image differs")
    identity = entry.get("source_identity", {})
    if any(identity.get(key) != mapping.get(key) for key in
           ("dataset_base", "actor_head", "actor_tree", "actor_image_id")):
        raise ValueError("Public frontend does not bind this original actor setup")
    if any(re.fullmatch(r"[0-9a-f]{40}", mapping.get(key, "")) is None
           for key in ("dataset_base", "actor_head", "actor_tree")):
        raise ValueError("Original public task and setup commit identities are required")
    argv = repository_frontend(public_task["repo"], python)
    if entry.get("argv") != argv:
        raise ValueError("Only the repository-wide public frontend is allowed; no selected test targets")
    visible = {"cwd": "/testbed", "python": python, "public_test_frontend": argv}
    text = ("Public execution facts:\nWorking directory: /testbed\nTask interpreter: " + python
            + "\nRepository-wide public test frontend: " + shlex.join(argv)
            + "\nUse this same interpreter for reproduction scripts and module invocations. "
              "The native terminal may report its current Python path; if it differs, "
              "use the absolute task interpreter above. Public frontend qualification "
              "was based on repository/interpreter family representatives, not a run "
              "of every task's full suite. Choose test targets from the original issue "
              "and public checkout only. A missing dependency, collection error, timeout "
              "or unexecuted test is not a passing test.\n\n" + TERMINAL_GUIDANCE)
    return {"version": VERSION, "instance_id": public_task["instance_id"],
            "repo": public_task["repo"], "visible_text": text, "visible_facts": visible,
            "sources": {"registry": registry_reference, "baseline_mapping": baseline_mapping_reference,
                        "adapter": reference(__file__)},
            "hidden_material_used": False, "task_specific_test_targets_added": False,
            "original_problem_statement_changed": False, "model_calls": 0}


def terminal_initialization_action(public_environment):
    """Construct one native action to run after the interactive shell starts.

    Bash -i can read image startup files that replace the initially supplied
    PATH. This explicitly restores only public interpreter-selection variables
    in that same terminal; it neither edits startup files nor runs on the host.
    """
    _, environment = _environment(public_environment)
    keys = [key for key in ("PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV") if key in environment]
    exports = " ".join(key + "=" + shlex.quote(environment[key]) for key in keys)
    probe = "import sys; print(" + repr(PROBE_MARKER) + " + sys.executable)"
    return {"command": "export " + exports + " && hash -r && python -c " + shlex.quote(probe),
            "timeout": 10}


def _observation_text(observation):
    content = observation.get("content", [])
    if not isinstance(content, list):
        return ""
    return "".join(item["text"] for item in content
                   if isinstance(item, dict) and item.get("type") == "text"
                   and isinstance(item.get("text"), str))


def validate_terminal_initialization(response, *, public_environment):
    python, _ = _environment(public_environment)
    observation = response.get("observation", {})
    metadata = observation.get("metadata", {})
    proof_lines = [line.strip() for line in _observation_text(observation).splitlines()
                   if line.strip().startswith(PROBE_MARKER)]
    if (response.get("type") != "observation" or response.get("tool") != "terminal"
            or observation.get("is_error") is not False or observation.get("timeout") is not False
            or observation.get("exit_code") != 0 or metadata.get("exit_code") != 0
            or observation.get("command") != terminal_initialization_action(public_environment)["command"]
            or metadata.get("py_interpreter_path") != python
            or proof_lines != [PROBE_MARKER + python]):
        raise ValueError("Actual native terminal did not establish the admitted task interpreter")
    return {"version": VERSION, "public_python": python, "native_shell_python_matches": True,
            "executed_python_matches": True, "original_permissions_retained": True,
            "public_tests_run": 0, "model_calls": 0}


def project_terminal_feedback(response, *, public_python):
    """Append fixed advice to a copy; retain raw RPC and native observation.

    This is an explicitly changed FIX observation, not unchanged upstream tool
    output. No input command is parsed, accepted, rejected, executed or retried.
    """
    python = _public_python(public_python)
    projected, events = copy.deepcopy(response), []
    if response.get("type") != "observation" or response.get("tool") != "terminal":
        return {"response": projected, "events": events}
    observation = response.get("observation", {})
    metadata = observation.get("metadata", {})
    text = _observation_text(observation)
    if (observation.get("is_error") is True and observation.get("exit_code") is None
            and metadata.get("exit_code", -1) == -1 and metadata.get("pid", -1) == -1
            and text.startswith(MULTI_COMMAND_PREFIX)):
        projected["llm_content"].append({"type": "text", "text": MULTI_COMMAND_GUIDANCE})
        events.append({"kind": "native_multiple_commands_feedback", "request_id": response.get("id"),
                       "command_rewritten": False, "automatic_retry": False})
    observed_python = metadata.get("py_interpreter_path")
    if observed_python is not None and observed_python != python:
        projected["llm_content"].append({"type": "text", "text": (
            "[v062 public environment feedback] The native terminal reports a Python "
            "path different from the admitted task interpreter. Use " + shlex.quote(python)
            + " explicitly for repository scripts and tests. This note did not change "
              "your shell or rerun the command; preserve and inspect the original result.")})
        events.append({"kind": "native_python_path_difference", "request_id": response.get("id"),
                       "command_rewritten": False, "automatic_retry": False})
    return {"response": projected, "events": events}

"""CPU source-projection controls; no actor, model or official tests execute."""
import copy
import json

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim import software_benchmark_public_context_v062 as context

PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
CANARY = "PRIVATE_INFORMATION_MUST_NOT_REACH_MODEL"


def environment():
    return {"kind": "official_image", "image_id": "sha256:" + "a" * 64,
            "source_config_sha256": "a" * 64, "public_python": PYTHON,
            "environment": {"PATH": str(context.PurePosixPath(PYTHON).parent) + ":/usr/bin:/bin",
                            "CONDA_PREFIX": "/opt/miniconda3/envs/testbed",
                            "CONDA_DEFAULT_ENV": "testbed", "IGNORED_SECRET": CANARY}}


def sources(tmp_path, *, repo="sympy/sympy", overrides=None):
    task = {"instance_id": "public-fixture", "repo": repo, "base_commit": "b" * 40,
            "problem_statement": "A public issue with multiple behaviors.", "ignored": CANARY}
    mapping = {"instance_id": task["instance_id"], "repo": repo,
               "dataset_base": task["base_commit"], "actor_head": "c" * 40,
               "actor_tree": "d" * 40, "actor_image_id": environment()["image_id"],
               "public_python": PYTHON, "gold_patch": CANARY, "eval_script": CANARY}
    mapping_ref = write_new(tmp_path / "mapping.json", mapping)
    entry = {"instance_id": task["instance_id"], "repo": repo, "admitted": True,
             "source": "public_repository", "hidden_material_used": False,
             "selection": context.SELECTION, "cwd": "/testbed", "public_python": PYTHON,
             "argv": context.repository_frontend(repo, PYTHON), "baseline_mapping": mapping_ref,
             "source_identity": {key: mapping[key] for key in
                                 ("dataset_base", "actor_head", "actor_tree", "actor_image_id")},
             "FAIL_TO_PASS": CANARY, "PASS_TO_PASS": CANARY, "arbitrary_notes": CANARY,
             "public_python_version": CANARY}
    entry.update(overrides or {})
    registry = {"version": "software-benchmark-public-test-registry-v054", "planned_tasks": 500,
                "entries": [entry], "private": CANARY}
    return task, {"registry_reference": write_new(tmp_path / "registry.json", registry),
                  "baseline_mapping_reference": mapping_ref, "public_environment": environment()}


@pytest.mark.parametrize("repo,tail", [
    ("sympy/sympy", ["bin/test"]),
    ("django/django", ["tests/runtests.py", "--noinput", "--parallel", "1"]),
    ("synthetic/pytest-project", ["-m", "pytest"]),
])
def test_explicit_public_projection_has_no_private_canary_or_selected_target(tmp_path, repo, tail):
    task, arguments = sources(tmp_path, repo=repo)
    result = context.prepare_public_context(task, **arguments)
    model_visible = json.dumps({key: result[key] for key in ("visible_text", "visible_facts")})
    assert CANARY not in model_visible
    assert all(key not in model_visible for key in ("gold_patch", "FAIL_TO_PASS", "eval_script"))
    assert result["visible_facts"] == {
        "cwd": "/testbed", "python": PYTHON, "public_test_frontend": [PYTHON, *tail]}
    assert "family representatives" in result["visible_text"]
    assert "coverage checklist" not in result["visible_text"]
    assert result["hidden_material_used"] is False


@pytest.mark.parametrize("overrides", [
    {"hidden_material_used": True}, {"source": "official_scoring"},
    {"argv": [PYTHON, "bin/test", "test_answer_selected.py"]},
    {"argv": [PYTHON, "-c", CANARY]}, {"public_python": "/usr/bin/python"},
    {"source_identity": {"actor_image_id": "sha256:" + "f" * 64}},
])
def test_untrusted_sources_or_task_selected_frontends_are_rejected(tmp_path, overrides):
    task, arguments = sources(tmp_path, overrides=overrides)
    with pytest.raises(ValueError):
        context.prepare_public_context(task, **arguments)


def terminal_response(*, text="", command="python -V", error=False,
                      python=PYTHON, exit_code=0, pid=123):
    return {"type": "observation", "tool": "terminal", "id": 4,
            "observation": {"is_error": error, "command": command, "timeout": False,
                            "exit_code": exit_code,
                            "metadata": {"exit_code": exit_code, "pid": pid,
                                         "py_interpreter_path": python},
                            "content": [{"type": "text", "text": text}]},
            "llm_content": [{"type": "text", "text": "native original " + text}]}


def test_interpreter_initialization_requires_actual_execution_and_shell_metadata():
    public = environment()
    original = copy.deepcopy(public)
    action = context.terminal_initialization_action(public)
    assert action["command"].startswith("export PATH=")
    assert "&& hash -r && python -c " in action["command"]
    assert CANARY not in action["command"] and public == original
    response = terminal_response(command=action["command"], text=context.PROBE_MARKER + PYTHON)
    assert context.validate_terminal_initialization(response, public_environment=public)[
        "executed_python_matches"] is True
    response["observation"]["metadata"]["py_interpreter_path"] = "/opt/miniconda3/bin/python"
    with pytest.raises(ValueError, match="Actual native terminal"):
        context.validate_terminal_initialization(response, public_environment=public)
    response["observation"]["metadata"]["py_interpreter_path"] = PYTHON
    response["observation"]["content"][0]["text"] = context.PROBE_MARKER + "/usr/bin/python"
    with pytest.raises(ValueError, match="Actual native terminal"):
        context.validate_terminal_initialization(response, public_environment=public)


def test_interpreter_environment_never_accepts_host_paths_or_wrong_path_order():
    for path in ("/usr/bin:/bin", "/opt/miniconda3/envs/testbed/bin:/data0/private",
                 "/opt/miniconda3/envs/testbed/bin::/bin"):
        public = environment()
        public["environment"]["PATH"] = path
        with pytest.raises(ValueError):
            context.terminal_initialization_action(public)


def test_only_actual_preexecution_refusal_gets_advice_and_raw_bytes_are_retained():
    response = terminal_response(text=context.MULTI_COMMAND_PREFIX + "(1) pwd\n(2) ls",
                                 command="pwd\nls", error=True, python=None,
                                 exit_code=None, pid=-1)
    response["observation"]["metadata"]["exit_code"] = -1
    original = copy.deepcopy(response)
    result = context.project_terminal_feedback(response, public_python=PYTHON)
    assert response == original
    assert result["response"]["observation"] == response["observation"]
    assert result["response"]["llm_content"][:-1] == response["llm_content"]
    assert result["response"]["llm_content"][-1]["text"] == context.MULTI_COMMAND_GUIDANCE
    assert result["events"] == [{"kind": "native_multiple_commands_feedback", "request_id": 4,
                                 "command_rewritten": False, "automatic_retry": False}]
    # A program printing the same prefix after executing is not a tool-format refusal.
    response["observation"]["metadata"].update(exit_code=1, pid=123)
    response["observation"]["exit_code"] = 1
    assert context.project_terminal_feedback(response, public_python=PYTHON)["events"] == []


def test_existing_allowed_commands_and_pending_results_are_not_reinterpreted():
    for command in ("pwd && ls", "pwd; ls", "python - <<'PY'\nprint('ok')\nPY", ""):
        response = terminal_response(command=command)
        assert context.project_terminal_feedback(response, public_python=PYTHON) == {
            "response": response, "events": []}
    pending = terminal_response(exit_code=-1)
    assert context.project_terminal_feedback(pending, public_python=PYTHON)["events"] == []


def test_python_drift_adds_advice_without_environment_change_or_command_retry():
    response = terminal_response(python="/opt/miniconda3/bin/python", exit_code=1)
    original = copy.deepcopy(response)
    result = context.project_terminal_feedback(response, public_python=PYTHON)
    assert response == original and result["response"]["observation"] == original["observation"]
    assert result["events"][0]["kind"] == "native_python_path_difference"
    assert result["events"][0]["automatic_retry"] is False
    assert PYTHON in result["response"]["llm_content"][-1]["text"]

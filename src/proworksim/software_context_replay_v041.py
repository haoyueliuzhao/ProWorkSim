"""Shared CPU-only native rendering/tokenizer measurements for v041 P0-A/B/C.

This loads the original local tokenizer and invokes the same native renderer as
the resident 9B actor. It never loads a model, adapter, optimizer or checkpoint.
All reported token counts encode the complete native request, not summed parts.
"""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace

from .software_context_v034 import project_software_request as old_project
from .software_context_v041 import project_software_request as new_project
from .storage import digest, json_bytes, read_json

VERSION = "software-native-context-measurement-v0.41"
SOURCE = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = SOURCE / "runs/software-organization-v040/plan.json"
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "vocab.json", "merges.txt", "config.json")


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def _checked(ref):
    path = Path(ref["path"])
    if digest(path.read_bytes()) != ref["sha256"]:
        raise ValueError("Frozen input identity changed: " + str(path))
    return path


def load_native_measurement(plan_path=DEFAULT_PLAN):
    plan_path = Path(plan_path).resolve()
    plan = read_json(plan_path)
    owner_path = _checked(plan["model_references"]["owner"])
    owner = read_json(owner_path)
    manifest_path = _checked(plan["model_references"]["base_manifest"])
    manifest = read_json(manifest_path)
    model_root = Path(owner["base_identity"]["path"])
    profile, recipe = owner["inference_profile"], owner["recipe"]
    if (profile.get("candidate_id") != "qwen3.5-9b" or profile.get("native_tool_prompt") != "official_xml_single_call"
            or recipe["max_length"] != 16384 or recipe["max_output_tokens"] != 2048
            or profile["chat_template_kwargs"] != {"enable_thinking": False, "preserve_thinking": False}
            or manifest.get("status") != "complete" or Path(manifest["model_path"]).resolve() != model_root.resolve()):
        raise ValueError("Require the frozen original 9B native renderer/tokenizer and 16384/2048 bounds")
    files = {}
    for name in TOKENIZER_FILES:
        path = model_root / name
        actual = reference(path)
        if actual["sha256"] != manifest["files"][name]["sha256"] or actual["bytes"] != manifest["files"][name]["bytes"]:
            raise ValueError("Original tokenizer input changed: " + name)
        files[name] = actual
    dependency_path = str(Path(plan["runtime_dependency_path"]).resolve())
    if dependency_path not in sys.path:
        sys.path.insert(0, dependency_path)
    import transformers
    from transformers import AutoTokenizer
    from .candidate_runtime_v015 import prepare_candidate_prompt

    if transformers.__version__ != profile["transformers"]:
        raise ValueError("Use the same frozen Transformers tokenizer version as v040")
    tokenizer = AutoTokenizer.from_pretrained(model_root, local_files_only=True, trust_remote_code=False)

    def render(request):
        return prepare_candidate_prompt(request, tokenizer, profile)

    identity = {"version": VERSION, "plan": reference(plan_path), "owner": reference(owner_path),
        "base_manifest": reference(manifest_path), "tokenizer_files": files,
        "tokenizer_class": type(tokenizer).__name__, "transformers_version": transformers.__version__,
        "transformers_module": str(Path(transformers.__file__).resolve()),
        "renderer": "proworksim.candidate_runtime_v015.prepare_candidate_prompt",
        "renderer_source": reference(SOURCE / "src/proworksim/candidate_runtime_v015.py"),
        "chat_template_kwargs": copy.deepcopy(profile["chat_template_kwargs"]),
        "context_limit": 16384, "reserved_output_tokens": 2048,
        "new_model_calls": 0, "model_weights_loaded": False, "new_backward_calls": 0,
        "scope": "Actual complete native rendering and original tokenizer only; no model/adapter/checkpoint load, sampler, probability or GPU operation"}
    return SimpleNamespace(tokenizer=tokenizer, render=render, prepare_request=render, identity=identity,
        recipe=copy.deepcopy(recipe), inference_profile=copy.deepcopy(profile))


def encode_request(request, measurement):
    if request.get("max_tokens") != 2048:
        raise ValueError("P0 capacity measurements must keep the fixed 2048 output reservation")
    rendered, messages, native = measurement.render(request)
    input_ids = measurement.tokenizer(rendered, add_special_tokens=False)["input_ids"]
    headroom = measurement.recipe["max_length"] - request["max_tokens"] - len(input_ids)
    return {"rendered_prompt": rendered, "native_messages": messages, "native_projection": native,
        "input_ids": input_ids, "prompt_tokens": len(input_ids),
        "rendered_prompt_sha256": digest(rendered.encode()), "input_ids_sha256": digest(json_bytes(input_ids)),
        "reserved_output_tokens": request["max_tokens"], "context_limit": measurement.recipe["max_length"],
        "headroom_tokens": headroom, "fits": headroom >= 0}


def measure_request(request, measurement):
    options = {"render": measurement.render, "tokenizer": measurement.tokenizer,
               "context_limit": measurement.recipe["max_length"]}
    old_selected, old_projection = old_project(request, **options)
    new_selected, new_projection = new_project(request, **options)
    result = {"original": {"request": copy.deepcopy(request), "encoding": encode_request(request, measurement)},
        "old": {"selected": old_selected, "projection": old_projection, "encoding": encode_request(old_selected, measurement)},
        "new": {"selected": new_selected, "projection": new_projection, "encoding": encode_request(new_selected, measurement)},
        "native_measurement_identity": copy.deepcopy(measurement.identity)}
    for key in ("old", "new"):
        projection, encoding = result[key]["projection"], result[key]["encoding"]
        if (projection["selected_prompt_tokens"] != encoding["prompt_tokens"]
                or projection["rendered_prompt_sha256"] != encoding["rendered_prompt_sha256"]
                or projection["input_ids_sha256"] != encoding["input_ids_sha256"]):
            raise ValueError("Full native encoding and projection measurement disagree")
    return result

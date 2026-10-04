"""Actual SDK/read/error CPU controls for only the two changed native interfaces."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys

from scripts import qualify_code_templates_v030 as original
from proworksim.audit import code_identity
from proworksim.candidate_runtime_v030 import MistralNativeTokenizer
from proworksim.candidate_runtime_v031 import CandidateActor, candidate_profile
from proworksim.native_codecs_v031 import xml_call_text
from proworksim.software_collaboration_v030 import CASE_IDS
from proworksim.storage import read_json

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ("swe-next-14b", "devstral-small-2507")
VERSION = "native-code-template-sdk-cpu-qualification-v0.31"
ORIGINAL_OUTPUT = original.scripted_native_output
REQUIRED = [*original.REQUIRED_SOURCE, "scripts/qualify_code_templates_v031.py",
            "src/proworksim/candidate_runtime_v031.py", "src/proworksim/native_codecs_v031.py",
            "src/proworksim/functional_dense_v031.py"]


class FixtureRenderer(CandidateActor):
    def prepare_request(self, request):
        self.fixture_request = copy.deepcopy(request)
        return super().prepare_request(request)


def scripted_native_output(candidate, renderer, name, arguments):
    if candidate == "swe-next-14b":
        raw = xml_call_text(name, arguments, renderer.fixture_request) + "<|im_end|>"
        return raw, renderer.tokenizer(raw, add_special_tokens=False)["input_ids"], "declared_author_openhands_xml_content_v031"
    return ORIGINAL_OUTPUT(candidate, renderer, name, arguments)


def renderer_for(candidate, assets):
    from transformers import AutoTokenizer
    renderer = object.__new__(FixtureRenderer)
    renderer.inference_profile = candidate_profile(candidate)
    root = Path(assets) / (candidate + "-" + renderer.inference_profile["revision"][:12])
    renderer.tokenizer = (MistralNativeTokenizer(root) if candidate == "devstral-small-2507" else
                         AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False))
    names = ("tekken.json", "config.json") if candidate == "devstral-small-2507" else (
        "tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "vocab.json", "merges.txt",
        "config.json", "added_tokens.json", "special_tokens_map.json")
    return renderer, {name: original.reference(root / name) for name in names if (root / name).exists()}


def qualify(output, asset_root):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    from proworksim import software_tasks_v030 as tasks
    source_files = {name: original.reference(ROOT / name) for name in REQUIRED}
    assets = {str(path.relative_to(ROOT)): original.reference(path)
              for path in sorted(tasks.ASSETS.rglob("*")) if path.is_file()}
    manifest = read_json(tasks.ASSETS / "source-manifest.json")
    upstream = ROOT / manifest["source"]["source_relative_path"]
    upstream_files = {str((upstream / name).relative_to(ROOT)): original.reference(upstream / name)
                      for name in manifest["source"]["files_sha256"]}
    report = {"version": VERSION, "started_at": datetime.now(timezone.utc).isoformat(),
              "source": code_identity(), "passed": False, "model_calls": 0, "gpu_used": False,
              "model_weights_loaded": False, "optimizer_updates": 0, "training_token_traces": 0,
              "trainable_rollouts_created": 0, "max_context_tokens": 16384, "reserved_output_tokens": 2048,
              "required_source_files": source_files, "required_development_assets": assets,
              "required_upstream_source_files": upstream_files, "tokenizer_files": {}, "controls": [],
              "scope": "Two changed interfaces × six unchanged development contracts. Reuses the real SDK/WorldCore fixture machinery with a declared v031 XML fixture encoder; no real model sampling or inference/training capability claim. The unchanged 9B is not rerun."}
    def write():
        original.write(output / "qualification.json", report)

    write()
    try:
        renderers = {}
        for candidate in CANDIDATES:
            renderers[candidate], report["tokenizer_files"][candidate] = renderer_for(candidate, asset_root)
        # This substitution changes only this process's explicit CPU response
        # program. Production actor/parser/world implementations remain intact.
        original.scripted_native_output = scripted_native_output

        def controls(candidate):
            return [original.qualify_case(candidate, renderers[candidate], case,
                                          output / candidate / case) for case in CASE_IDS]

        with ThreadPoolExecutor(max_workers=2) as pool:
            for rows in pool.map(controls, CANDIDATES):
                report["controls"].extend(rows)
                write()
        measurements = [row for control in report["controls"] for row in control["measurements"]]
        report.update(combination_count=len(report["controls"]),
            scripted_sdk_transport_calls=sum(row["scripted_sdk_transport_calls"] for row in report["controls"]),
            native_roundtrip_count=sum(row["native_codec_roundtrip"] for row in measurements),
            actual_world_error_count=sum(len(row["actual_world_errors"]) for row in report["controls"]),
            error_feedback_next_request_count=sum(row["error_feedback_next_request_count"] for row in report["controls"]),
            minimum_remaining_margin_tokens=min(row["remaining_context_after_output_reservation"] for row in measurements),
            maximum_selected_prompt_tokens=max(row["prompt_tokens"] for row in measurements),
            projected_request_count=sum(bool(row["removed_indices"]) for row in measurements), source_after=code_identity())
        refs = [*source_files.values(), *assets.values(), *upstream_files.values(),
                *(ref for files in report["tokenizer_files"].values() for ref in files.values())]
        report["required_files_unchanged"] = all(original.reference(ref["path"]) == ref for ref in refs)
        report["whole_source_tree_unchanged"] = report["source"]["source_tree_sha256"] == report["source_after"]["source_tree_sha256"]
        torch = sys.modules.get("torch")
        report["torch_cuda_initialized"] = bool(torch is not None and torch.cuda.is_initialized())
        report["passed"] = (report["combination_count"] == 12 and all(row["passed"] for row in report["controls"])
            and report["scripted_sdk_transport_calls"] == report["native_roundtrip_count"] == 48
            and report["actual_world_error_count"] == report["error_feedback_next_request_count"] == 16
            and report["required_files_unchanged"] and report["whole_source_tree_unchanged"]
            and not report["torch_cuda_initialized"])
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        original.scripted_native_output = ORIGINAL_OUTPUT
        report["ended_at"] = datetime.now(timezone.utc).isoformat()
        write()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.output, args.asset_root)
    print({key: result.get(key) for key in ("passed", "combination_count", "native_roundtrip_count",
          "actual_world_error_count", "minimum_remaining_margin_tokens", "maximum_selected_prompt_tokens")})
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Build an independent code revision with explicit shared data paths; no service operations."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

ORIGINAL = Path("/data0/zhuxinrui/projects/ProWorkSim")


def ref(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def create(source_root, extra_roots):
    source_root = source_root.resolve()
    if (source_root.exists() or not source_root.is_relative_to(
            ORIGINAL / "runs/software-benchmark-v054/kernel-optimization-r1")):
        raise ValueError("Use one fresh independent kernel revision directory")
    source_root.mkdir(parents=True)
    files = {}
    for directory, pattern in (("src", "*.py"), ("scripts", "*.py"), ("config", "v054-*.json")):
        for path in (ORIGINAL / directory).rglob(pattern):
            if "__pycache__" not in path.parts:
                files[str(path.relative_to(ORIGINAL))] = path
    for pattern in ("*v054*.py", "*v054*.sh"):
        for path in (ORIGINAL / "tools").glob(pattern):
            files[str(path.relative_to(ORIGINAL))] = path
    for extra in extra_roots:
        for prefix in ("src", "tools"):
            for path in (extra / prefix).rglob("*"):
                if path.is_file() and path.suffix in {".py", ".sh"}:
                    files[str(path.relative_to(extra))] = path
    records = []
    root_pattern = re.compile(r"(?m)^(ROOT\s*=\s*)Path\(__file__\)\.resolve\(\)\.parents\[[12]\]\s*$")
    for relative, path in sorted(files.items()):
        target = source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        original = path.read_text()
        text = root_pattern.sub(lambda match: match[1] + "Path(" + repr(str(ORIGINAL)) + ")", original)
        if relative == "src/proworksim/software_benchmark_episode_v054.py":
            text = text.replace('Path(__file__).resolve().parents[2] / "runs/software-benchmark-v054/episode-claims"',
                                "Path(" + repr(str(ORIGINAL / "runs/software-benchmark-v054/episode-claims")) + ")")
        # Tools executed by the original worker's Python argv must explicitly
        # select this copied package; data and shared leases still use ORIGINAL.
        if (relative.startswith("tools/") and target.suffix == ".py"
                and target.name != "prepare_kernel_source_root_v054.py"):
            text = text.replace('ROOT / "src"', "Path(" + repr(str(source_root / "src")) + ")")
            text = text.replace("ROOT/'src'", "Path(" + repr(str(source_root / "src")) + ")")
            text = text.replace("ROOT / 'src'", "Path(" + repr(str(source_root / "src")) + ")")
            text = text.replace("str(ROOT)]", "str(Path(" + repr(str(source_root)) + "))]")
            tree = ast.parse(text)
            insert = 0
            if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
                insert = tree.body[0].end_lineno
            for node in tree.body:
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    insert = node.end_lineno
            lines = text.splitlines(keepends=True)
            lines[insert:insert] = ["import sys as _revision_sys\n",
                "_revision_sys.path.insert(0, " + repr(str(source_root / "src")) + ")\n",
                "_revision_sys.path.insert(1, " + repr(str(source_root)) + ")\n"]
            text = "".join(lines)
        target.write_text(text)
        if target.suffix == ".sh":
            shutil.copymode(path, target)
        records.append({"original": ref(path), "copied": ref(target),
                        "shared_data_root_only_relocation": text != original})
    # Conditions and source manifest are private to this revision. No canonical
    # condition/source path is overwritten, and old workers see old bytes.
    factory = source_root / "src/proworksim/software_benchmark_service_factory_v054.py"
    text = factory.read_text()
    needle = 'return reference(ROOT / ("config/v054-condition-" + arm + ".json"))'
    if text.count(needle) != 1:
        raise ValueError("Fixed condition selector changed; do not guess its replacement")
    text = text.replace(needle, 'return reference(Path(' + repr(str(source_root))
                        + ') / ("config/v054-condition-" + arm + ".json"))')
    # Sentinel must import the same revision's explicit new pool guard.
    text = text.replace('ROOT / "tools/hold_resident_session_v054.py"',
                        "Path(" + repr(str(source_root / "tools/hold_resident_session_v054.py")) + ")")
    factory.write_text(text)
    runner = source_root / "src/proworksim/software_benchmark_runner_v054.py"
    text = runner.read_text()
    needle = 'ROOT / "tools/run_benchmark_controller_v054.py"'
    if text.count(needle) != 1:
        raise ValueError("Expected unique native controller source selector")
    runner.write_text(text.replace(needle, "Path(" + repr(str(source_root /
        "tools/run_benchmark_controller_v054.py")) + ")"))
    freeze = source_root / "src/proworksim/software_benchmark_source_freeze_v054.py"
    text = freeze.read_text().replace('MANIFEST = ROOT / "artifacts/software-benchmark-v054/runner/source-manifest.json"',
        "MANIFEST = Path(" + repr(str(source_root / "artifacts/software-benchmark-v054/runner/source-manifest.json")) + ")")
    text = text.replace('paths = set((ROOT / "src/proworksim").rglob("*.py"))',
        'paths = set((ROOT / "src/proworksim").rglob("*.py"))\n'
        '    for directory, pattern in (("src", "*.py"), ("scripts", "*.py"), ("tools", "*v054*.py")):\n'
        '        paths.update((Path(' + repr(str(source_root)) + ') / directory).rglob(pattern))')
    freeze.write_text(text)
    # The new numerical qualifier extends identity. Preserve it on actual
    # CalibrationActor facades without replacing generate_native or sampling.
    interleave = source_root / "src/proworksim/software_benchmark_interleaved_owner_v054.py"
    text = interleave.read_text()
    needle = '            if (actor.model is not self.model or actor.generate_native.__func__ is not CalibrationActor.generate_native'
    extension = ('            if self.owner_identity.get("kernel_runtime") is not None:\n'
        '                actor.inference_profile = copy.deepcopy(self.owner.inference_profile)\n'
        '                actor.inference_profile_sha256 = self.owner.inference_profile_sha256\n'
        '                actor._identity = copy.deepcopy(self.owner_identity)\n')
    if text.count(needle) != 1:
        raise ValueError("Expected explicit CalibrationActor facade guard")
    interleave.write_text(text.replace(needle, extension + needle))
    # Extend only the copied pool validator for this explicit singleton successor.
    pool = source_root / "src/proworksim/software_benchmark_resident_pool_v054.py"
    text = pool.read_text()
    text = text.replace('INTERLEAVED_POLICY_VERSION = "v054-resident-pool-policy-v2-interleaved"',
        'INTERLEAVED_POLICY_VERSION = "v054-resident-pool-policy-v2-interleaved"\n'
        'KERNEL_POLICY_VERSION = "v054-resident-pool-policy-v3-kernel-g6"')
    text = text.replace('interleaved = policy.get("version") == INTERLEAVED_POLICY_VERSION',
        'kernel = policy.get("version") == KERNEL_POLICY_VERSION\n'
        '    interleaved = policy.get("version") in {INTERLEAVED_POLICY_VERSION, KERNEL_POLICY_VERSION}')
    text = text.replace('policy.get("inherit_modes") != ["REF"]',
        'policy.get("inherit_modes") != ([] if kernel else ["REF"])')
    text = text.replace('{POLICY_VERSION, INTERLEAVED_POLICY_VERSION}',
        '{POLICY_VERSION, INTERLEAVED_POLICY_VERSION, KERNEL_POLICY_VERSION}')
    text = text.replace('policy.get("physical_gpus") != list(range(8))',
        'policy.get("physical_gpus") != ([6] if kernel else list(range(8)))')
    text = text.replace('policy.get("maximum_residents") != 8',
        'policy.get("maximum_residents") != (1 if kernel else 8)')
    text = text.replace('policy.get("ref_to_mp_after_all_500_scored") is not True',
        'policy.get("ref_to_mp_after_all_500_scored") is not (False if kernel else True)')
    needle = '    return policy\n\n\ndef _static_registration'
    text = text.replace(needle, '    if kernel:\n        checked(policy["kernel_plan"])\n        checked(policy["original_pool_policy"])\n        if (policy.get("runtime_revision") != "FLA-only-kernel-g6-r1"\n                or policy.get("maximum_kernel_qualification_requests") != 6\n                or policy.get("automatic_provisioner") is not False):\n            raise ValueError("Unrecognized isolated kernel successor policy")\n    return policy\n\n\ndef _static_registration')
    needle = '    return event\n\ndef read_pool'
    # The actual source includes three newlines at this boundary.
    insert = '    if kernel:\n        spec = read_ref(event["source_spec"])\n        evidence = live_identity.get("actor_identity", {}).get("kernel_runtime")\n        if (event["gpu_index"] != 6 or event["mode"] != "MATCH_PROJECT"\n                or spec.get("kernel_plan") != policy["kernel_plan"]\n                or not evidence or evidence.get("plan") != policy["kernel_plan"]\n                or evidence != ready.get("kernel_runtime")\n                or admission.get("kernel_runtime") != evidence):\n            raise ValueError("Kernel registration lost its separately qualified numerical identity")\n        qualifier = read_ref(evidence["qualification"])\n        if (qualifier.get("passed") is not True or qualifier.get("actual_model_requests") != 6\n                or qualifier.get("model_loads") != 1 or qualifier.get("formal_tasks_used") != 0):\n            raise ValueError("Kernel registration lacks its fixed model diagnostics")\n'
    needle = '    return event\n\n\ndef read_pool'
    if text.count(needle) != 1:
        raise ValueError("Expected static registration return")
    pool.write_text(text.replace(needle, insert + needle))
    # Assembly records represent the final copy after these explicit transforms.
    records = [{**record, "copied": ref(Path(record["copied"]["path"]))} for record in records]
    result = {"version": "v054-kernel-source-root-r1", "source_root": str(source_root),
        "shared_data_root": str(ORIGINAL), "old_sources_modified": False,
        "files": records, "assembly_complete": True, "formal_admission_passed": False,
        "large_assets_copied": False, "model_calls": 0,
        "required_final_steps": ["bind exact kernel plan and dependency manifest",
            "freeze independent conditions/source/bindings after deployment integration",
            "single-GPU boundary release, model diagnostic and six-request owner qualification"]}
    path = source_root / "assembly.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    return ref(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--extra-source-root", action="append", type=Path, default=[])
    args = parser.parse_args()
    print(json.dumps(create(args.source_root, args.extra_source_root)))


if __name__ == "__main__":
    os.umask(0o077)
    main()

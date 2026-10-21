"""Write the two fixed resident deployments and launch argv; never load a model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_match_v054 import CONTRACT
from proworksim.software_benchmark_service_factory_v054 import (
    MODEL, ROOT, capacity_admission, condition_reference, ref_arguments,
)
from proworksim.storage import digest, json_bytes
from tools.prepare_model_capacity_v054 import gpu_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ref-capacity", required=True, type=Path)
    parser.add_argument("--match-capacity", required=True, type=Path)
    parser.add_argument("--ref-preparation-permit", required=True, type=Path)
    parser.add_argument("--match-preparation-permit", required=True, type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Resident declarations must be private project run assets")
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    capacity = {"REF": reference(args.ref_capacity), "MATCH_PROJECT": reference(args.match_capacity)}
    preparation = {"REF": reference(args.ref_preparation_permit),
                   "MATCH_PROJECT": reference(args.match_preparation_permit)}
    cards = {row["index"]: row for row in gpu_rows()}
    contract = write_new(root / "contract.json", CONTRACT)
    permit = write_new(root / "model-load-admission.json", {
        "model_loading_authorized": True, "model_manifest": reference(MODEL / "proworksim-manifest.json"),
        "contract_sha256": digest(json_bytes(CONTRACT)), "formal_execution_authorized": False})
    residents, launches = {}, {}
    for mode, index, suffix in (("REF", 7, "ref"), ("MATCH_PROJECT", 6, "mp")):
        admitted = capacity_admission("REF" if mode == "REF" else "MATCH", capacity[mode])
        directory = root / suffix
        short = ROOT / "runs/v054-gpu" / secrets.token_hex(4)
        unit = "proworksim-v054-resident-" + suffix + "-r1.service"
        spec = {"unit": unit, "root": str(directory), "short": str(short), "card": cards[index],
                "capacity_receipt": capacity[mode], "capacity_admission": admitted,
                "preparation_permit": preparation[mode],
                "model_manifest": reference(MODEL / "proworksim-manifest.json"),
                "identity_path": str(directory / "identity.json"), "ready_path": str(directory / "ready.json")}
        if mode == "REF":
            spec.update(arm="REF", condition=condition_reference("REF"), REF_argv=ref_arguments(),
                        api_key_file=str(directory / "api-key.private"))
            tool, flag = "tools/serve_ref_resident_v054.py", "--spec-sha256"
            admin = {"endpoint": "http://127.0.0.1:18054", "api_key_file": spec["api_key_file"]}
        else:
            spec.update(version="v054-match-resident-spec-v1", contract=contract, load_admission=permit,
                        sources=[reference(ROOT / name) for name in (
                            "tools/run_match_resident_v054.py", "tools/serve_resident_owner_v054.py",
                            "src/proworksim/software_benchmark_resident_owner_v054.py")])
            tool, flag = "tools/run_match_resident_v054.py", "--sha256"
            admin = {"socket_path": str(short / "admin.sock")}
        spec_ref = write_new(root / (suffix + "-spec.json"), spec)
        residents[mode] = write_new(root / (suffix + "-declaration.json"), {
            "version": "v054-resident-declaration-v1", "mode": mode, "gpu_index": index,
            "gpu_uuid": cards[index]["uuid"], "unit": unit, "source_spec": spec_ref,
            "ready_path": spec["ready_path"], "identity_path": spec["identity_path"],
            "session_lock_path": str(directory / "session.lock"), "admin": admin})
        launches[mode] = ["systemd-run", "--user", "--unit=" + unit,
            "--property=Restart=no", "--property=KillMode=control-group",
            "--property=WorkingDirectory=" + str(ROOT),
            "--setenv=PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
            str(ROOT / ".venv/bin/python"), str(ROOT / tool), "--spec", spec_ref["path"], flag, spec_ref["sha256"]]
    registry = write_new(root / "registry.json", {"version": "v054-resident-registry-v1", "residents": residents})
    instructions = write_new(root / "launch-argv.json", {"registry": registry, "commands": launches,
                             "automatic_start": False, "model_loads": 0})
    print(json.dumps({"registry": registry, "launch_argv": instructions, "automatic_start": False}))


if __name__ == "__main__":
    main()
